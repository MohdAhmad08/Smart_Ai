"""
backfill.py — Fast historical data bootstrap for Phase 2 (MySQL, parallel edition).

Architecture:
  - One process per machine (multiprocessing.Pool) → bypasses GIL, uses all cores
  - Each worker runs a writer thread alongside generation → DB I/O overlaps CPU
  - INSERT IGNORE for idempotency (safe to re-run)

Usage:
  python backfill.py
  GEN_DT_SECONDS=30 python backfill.py   # recommended: ~1.2M rows vs 12M

Key env vars:
  DATABASE_URL
  GEN_MACHINES   (default 5)
  GEN_SEED       (default 42)
  GEN_SIM_WEEKS  (default 12)
  GEN_DT_SECONDS (default 30)
  GEN_ACCEL      (default 3.0)
  GEN_BATCH_SIZE (default 500)
  GEN_WORKERS    (default = min(GEN_MACHINES, cpu_count))
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone, timedelta
from multiprocessing import Pool, cpu_count
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from machine_data_generator import SyntheticMachineGenerator

# Single project-wide .env lives at the repo root, regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

# ─── Config ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/machine_telemetry?charset=utf8mb4",
)
N_MACHINES   = int(os.getenv("GEN_MACHINES",      "5"))
MASTER_SEED  = int(os.getenv("GEN_SEED",           "42"))
SIM_WEEKS    = int(os.getenv("GEN_SIM_WEEKS",      "12"))
DT           = float(os.getenv("GEN_DT_SECONDS",   "30"))
ACCEL        = float(os.getenv("GEN_ACCEL",        "3.0"))
BATCH_SIZE   = int(os.getenv("GEN_BATCH_SIZE",     "500"))
N_WORKERS    = int(os.getenv("GEN_WORKERS",        str(min(N_MACHINES, cpu_count()))))
NO_CALENDAR  = os.getenv("GEN_NO_CALENDAR", "0").strip() in ("1", "true", "yes")

# ─── SQL strings (plain strings so they survive pickling across processes) ──
_SQL_CREATE_READINGS = """
    CREATE TABLE IF NOT EXISTS machine_readings (
        id               BIGINT       PRIMARY KEY AUTO_INCREMENT,
        session_id       VARCHAR(36)  NOT NULL,
        seq              INT          NOT NULL,
        machine_name     VARCHAR(64)  NOT NULL,
        state            VARCHAR(16)  NOT NULL,
        ts               DATETIME(3)  NOT NULL,
        lot_1            INT,
        lot_2            INT,
        article          VARCHAR(32),
        speed            FLOAT,
        length           FLOAT,
        lot_time_s       INT,
        machine_time_s   INT,
        steam_consumed_lot  FLOAT,
        water_consumed_lot  FLOAT,
        power_consumed_lot  FLOAT,
        air_consumed_lot    FLOAT,
        sf_flow          FLOAT,
        sf_tot           FLOAT,
        wat_flow         FLOAT,
        wat_tot          FLOAT,
        em_power         FLOAT,
        em_energy        FLOAT,
        vibration_rms    FLOAT,
        motor_current    FLOAT,
        bearing_temp     FLOAT,
        winding_temp     FLOAT,
        air_pressure     FLOAT,
        good_count       INT,
        reject_count     INT,
        truth_json       JSON,
        UNIQUE KEY uq_reading_session_seq (session_id, seq),
        KEY idx_reading_ts (ts),
        KEY idx_reading_machine (machine_name),
        KEY idx_reading_lot (lot_1)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_SQL_CREATE_RUNS = """
    CREATE TABLE IF NOT EXISTS machine_runs (
        id                     BIGINT      PRIMARY KEY AUTO_INCREMENT,
        session_id             VARCHAR(36) NOT NULL,
        machine_name           VARCHAR(64) NOT NULL,
        component              VARCHAR(32),
        severity               VARCHAR(16),
        run_start_ts           DATETIME(3),
        failure_ts             DATETIME(3),
        repair_ts              DATETIME(3),
        run_hours_to_failure   FLOAT,
        seq_at_failure         INT,
        KEY idx_run_session  (session_id),
        KEY idx_run_machine  (machine_name),
        KEY idx_run_failure  (failure_ts),
        KEY idx_run_component(component)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_SQL_CREATE_CHECKPOINT = """
    CREATE TABLE IF NOT EXISTS generator_state (
        machine_id  INT  PRIMARY KEY,
        state_json  JSON NOT NULL,
        saved_at    DATETIME(3) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_SQL_INSERT_READING = """
    INSERT IGNORE INTO machine_readings
        (session_id, seq, machine_name, state, ts,
         lot_1, lot_2, article, speed, length, lot_time_s, machine_time_s,
         steam_consumed_lot, water_consumed_lot, power_consumed_lot, air_consumed_lot,
         sf_flow, sf_tot, wat_flow, wat_tot, em_power, em_energy,
         vibration_rms, motor_current, bearing_temp, winding_temp, air_pressure,
         good_count, reject_count, truth_json)
    VALUES
        (:session_id, :seq, :machine_name, :state, :ts,
         :lot_1, :lot_2, :article, :speed, :length, :lot_time_s, :machine_time_s,
         :steam_consumed_lot, :water_consumed_lot, :power_consumed_lot, :air_consumed_lot,
         :sf_flow, :sf_tot, :wat_flow, :wat_tot, :em_power, :em_energy,
         :vibration_rms, :motor_current, :bearing_temp, :winding_temp, :air_pressure,
         :good_count, :reject_count, :truth_json)
"""

_SQL_INSERT_EVENT = """
    INSERT INTO machine_runs
        (session_id, machine_name, component, severity,
         run_start_ts, failure_ts, repair_ts,
         run_hours_to_failure, seq_at_failure)
    VALUES
        (:session_id, :machine_name, :component, :severity,
         :run_start_ts, :failure_ts, :repair_ts,
         :run_hours_to_failure, :seq_at_failure)
"""

_SQL_UPSERT_CHECKPOINT = """
    INSERT INTO generator_state (machine_id, state_json, saved_at)
    VALUES (:machine_id, :state_json, :saved_at)
    ON DUPLICATE KEY UPDATE
        state_json = VALUES(state_json),
        saved_at   = VALUES(saved_at)
"""


# ─── Flatten helpers ────────────────────────────────────────────────────────

def _hms_to_seconds(value) -> int:
    if not value:
        return 0
    try:
        parts = [int(p) for p in str(value).split(":")]
    except ValueError:
        return 0
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _to_f(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _flatten_reading(data: dict) -> dict:
    plc     = data.get("plc", {}) or {}
    util    = data.get("utility", {}) or {}
    health  = data.get("health", {}) or {}
    quality = data.get("quality", {}) or {}
    truth   = data.get("_truth")
    return {
        "session_id":   data["session_id"],
        "seq":          data["seq"],
        "machine_name": data["machine_name"],
        "state":        data.get("state", "idle"),
        "ts":           data["timestamp"],
        "lot_1":   plc.get("lot_1"),
        "lot_2":   plc.get("lot_2"),
        "article": plc.get("article"),
        "speed":   _to_f(plc.get("speed")),
        "length":  _to_f(plc.get("length")),
        "lot_time_s":     _hms_to_seconds(plc.get("lot_time")),
        "machine_time_s": _hms_to_seconds(plc.get("machine_time")),
        "steam_consumed_lot": _to_f(plc.get("steam_consumed_lot")),
        "water_consumed_lot": _to_f(plc.get("water_consumed_lot")),
        "power_consumed_lot": _to_f(plc.get("power_consumed_lot")),
        "air_consumed_lot":   _to_f(plc.get("air_consumed_lot")),
        "sf_flow":  _to_f(util.get("SF_Flow")),
        "sf_tot":   _to_f(util.get("SF_Tot")),
        "wat_flow": _to_f(util.get("Wat_Flow")),
        "wat_tot":  _to_f(util.get("Wat_Tot")),
        "em_power": _to_f(util.get("EM_Power")),
        "em_energy": _to_f(util.get("EM_Energy")),
        "vibration_rms": _to_f(health.get("vibration_rms")),
        "motor_current": _to_f(health.get("motor_current")),
        "bearing_temp":  _to_f(health.get("bearing_temp")),
        "winding_temp":  _to_f(health.get("winding_temp")),
        "air_pressure":  _to_f(health.get("air_pressure")),
        "good_count":   quality.get("good_count"),
        "reject_count": quality.get("reject_count"),
        "truth_json": json.dumps(truth) if truth is not None else None,
    }


def _flatten_event(data: dict) -> dict:
    return {
        "session_id":   data.get("session_id"),
        "machine_name": data.get("machine_name"),
        "component":    data.get("component"),
        "severity":     data.get("severity"),
        "run_start_ts": data.get("run_start_ts"),
        "failure_ts":   data.get("failure_ts"),
        "repair_ts":    data.get("repair_ts"),
        "run_hours_to_failure": data.get("run_hours_to_failure"),
        "seq_at_failure":       data.get("seq_at_failure"),
    }


# ─── Per-machine worker (runs in its own process) ──────────────────────────

def _machine_worker(args: tuple) -> dict:
    """
    Called in a subprocess via Pool.map.
    Returns a summary dict: {mid, readings, events, component_counts, elapsed_s}
    """
    (mid, machine_seed, sim_start_iso, ticks_per_machine,
     stagger, db_url, dt, accel, batch_size, no_calendar) = args

    sim_start = datetime.fromisoformat(sim_start_iso)
    machine_sim_start = sim_start - timedelta(seconds=stagger * dt)

    # Each process needs its own engine (engines are not fork-safe)
    engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600,
                           pool_size=2, max_overflow=0)
    ins_reading    = text(_SQL_INSERT_READING)
    ins_event      = text(_SQL_INSERT_EVENT)
    ups_checkpoint = text(_SQL_UPSERT_CHECKPOINT)

    # ── Writer thread: drains a queue → DB ──────────────────────────────
    write_queue: queue.Queue = queue.Queue(maxsize=8)  # backpressure: 8 batches
    write_errors = []

    def _writer():
        while True:
            item = write_queue.get()
            if item is None:  # sentinel
                write_queue.task_done()
                break
            r_batch, e_batch = item
            try:
                with engine.begin() as conn:
                    if r_batch:
                        conn.execute(ins_reading, r_batch)
                    if e_batch:
                        conn.execute(ins_event, e_batch)
            except Exception as exc:
                write_errors.append(str(exc))
            finally:
                write_queue.task_done()

    writer = threading.Thread(target=_writer, daemon=True)
    writer.start()

    # ── Generator setup ─────────────────────────────────────────────────
    gen = SyntheticMachineGenerator(
        machine_id=mid,
        seed=machine_seed,
        accel=accel,
        dt=dt,
        sim_start_ts=machine_sim_start,
        no_calendar=no_calendar,
    )

    # Fast-forward stagger ticks (ages components, output discarded)
    for _ in range(stagger):
        gen.generate_one()
        gen.pop_events()

    # Reset to clean history boundary
    gen.sim_ts    = sim_start
    gen.session_id = str(uuid.uuid4())
    gen.seq        = 0
    gen.steam_total    = 0.0
    gen.water_total    = 0.0
    gen.em_energy_kwh  = 0.0
    gen.length         = 0.0
    gen.lot_time_s     = 0.0
    gen._good_count    = 0
    gen._reject_count  = 0
    gen._current_run_start_ts              = sim_start.isoformat()
    gen._current_run_start_machine_time    = gen.machine_time_s
    gen._current_run_start_seq             = 0

    # ── Generation loop ─────────────────────────────────────────────────
    readings_buf: list[dict] = []
    events_buf:   list[dict] = []
    m_readings = 0
    m_events   = 0
    component_counts: Counter = Counter()
    wall_start = time.time()
    last_report = wall_start

    for tick in range(ticks_per_machine):
        readings_buf.append(_flatten_reading(gen.generate_one()))
        m_readings += 1

        for evt in gen.pop_events():
            events_buf.append(_flatten_event(evt))
            component_counts[evt.get("component", "unknown")] += 1
            m_events += 1

        if len(readings_buf) >= batch_size:
            write_queue.put((readings_buf, events_buf))
            readings_buf = []
            events_buf   = []

        now = time.time()
        if now - last_report >= 15:  # progress every 15s
            pct  = tick / ticks_per_machine * 100
            rate = m_readings / (now - wall_start)
            print(f"  [M{mid+1}] {pct:5.1f}%  {m_readings:,} readings  "
                  f"{rate:,.0f} r/s  queue={write_queue.qsize()}", flush=True)
            last_report = now

    # Flush remainder and stop writer
    if readings_buf or events_buf:
        write_queue.put((readings_buf, events_buf))
    write_queue.put(None)       # sentinel
    write_queue.join()          # wait for all writes to finish
    writer.join()

    if write_errors:
        print(f"  [M{mid+1}] WARN {len(write_errors)} write error(s): {write_errors[:3]}",
              flush=True)

    # Save checkpoint for live publisher handoff
    try:
        with engine.begin() as conn:
            conn.execute(ups_checkpoint, {
                "machine_id": gen.machine_id,
                "state_json": json.dumps(gen.serialize()),
                "saved_at":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            })
    except Exception as exc:
        print(f"  [M{mid+1}] checkpoint save failed: {exc}", flush=True)

    engine.dispose()

    elapsed = time.time() - wall_start
    print(f"  [M{mid+1}] OK {m_readings:,} readings  {m_events} events  "
          f"in {elapsed:.1f}s  ({m_readings/elapsed:,.0f} r/s)", flush=True)

    return {
        "mid": mid,
        "readings": m_readings,
        "events":   m_events,
        "component_counts": dict(component_counts),
        "elapsed_s": elapsed,
    }


# ─── Schema setup (runs in main process before workers start) ──────────────

def _create_tables(db_url: str) -> None:
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(_SQL_CREATE_READINGS))
        conn.execute(text(_SQL_CREATE_RUNS))
        conn.execute(text(_SQL_CREATE_CHECKPOINT))
    engine.dispose()
    print("Tables ensured.")


# ─── Main ──────────────────────────────────────────────────────────────────

def run_backfill() -> None:
    _create_tables(DATABASE_URL)

    sim_end   = datetime.now(timezone.utc)
    sim_start = sim_end - timedelta(weeks=SIM_WEEKS)
    ticks_per_machine = int(SIM_WEEKS * 7 * 24 * 3600 / DT)

    stagger_options = [
        0,
        ticks_per_machine // 7,
        ticks_per_machine // 5,
        ticks_per_machine // 4,
        ticks_per_machine // 3,
    ]

    print(f"\n{'='*65}")
    print(f"BACKFILL  machines={N_MACHINES}  workers={N_WORKERS}  "
          f"weeks={SIM_WEEKS}  dt={DT}s  accel={ACCEL}x  "
          f"no_calendar={NO_CALENDAR}")
    print(f"Sim range : {sim_start.date()} -> {sim_end.date()}")
    print(f"Ticks/machine : {ticks_per_machine:,}   "
          f"(~{ticks_per_machine * N_MACHINES / 1e6:.2f}M total readings)")
    print(f"{'='*65}\n")

    # Build argument list for each machine worker
    worker_args = [
        (
            mid,
            MASTER_SEED * 1000 + mid,
            sim_start.isoformat(),
            ticks_per_machine,
            stagger_options[mid % len(stagger_options)],
            DATABASE_URL,
            DT,
            ACCEL,
            BATCH_SIZE,
            NO_CALENDAR,
        )
        for mid in range(N_MACHINES)
    ]

    wall_start = time.time()

    with Pool(processes=N_WORKERS) as pool:
        results = pool.map(_machine_worker, worker_args)

    total_elapsed = time.time() - wall_start

    # Aggregate stats
    total_readings = sum(r["readings"] for r in results)
    total_events   = sum(r["events"]   for r in results)
    merged_counts: Counter = Counter()
    for r in results:
        merged_counts.update(r["component_counts"])

    print(f"\n{'='*65}")
    print(f"BACKFILL COMPLETE in {total_elapsed:.1f}s  "
          f"(wall-clock including parallel overlap)")
    print(f"  Total readings : {total_readings:,}")
    print(f"  Total events   : {total_events}")
    print(f"  Effective rate : {total_readings / total_elapsed:,.0f} readings/s")
    print(f"\n  Failure counts by component:")
    for comp, count in sorted(merged_counts.items()):
        print(f"    {comp:15s}: {count:4d} events")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    # Required on Windows (spawn start method) — must be inside this guard
    run_backfill()
