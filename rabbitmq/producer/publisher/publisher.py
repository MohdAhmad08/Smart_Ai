"""
publisher.py — Multi-machine live stream producer (MySQL edition).

Runs N SyntheticMachineGenerator instances on wall-clock time,
publishing telemetry on 'scada.tag.data' and failure/maintenance
events on 'scada.machine.event'. Checkpoints generator state to
the generator_state MySQL table every CHECKPOINT_EVERY readings
so a restart resumes cleanly from where it left off.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pika
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from machine_data_generator import SyntheticMachineGenerator

# Single project-wide .env lives at the repo root, regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

# ─── RabbitMQ ──────────────────────────────────────────────────────────────
RABBIT_USER     = os.getenv("RABBIT_MQ_USER")
RABBIT_PASS     = os.getenv("RABBIT_MQ_PASSWORD")
RABBIT_HOST     = os.getenv("RABBIT_MQ_HOST")
RABBIT_PORT     = int(os.getenv("RABBIT_MQ_PORT", "5672"))
EXCHANGE        = os.getenv("RABBIT_MQ_EXCHANGE",             "scada_data")
ROUTING_DATA    = os.getenv("RABBIT_MQ_ROUTING_KEY",          "scada.tag.data")
ROUTING_EVENT   = os.getenv("RABBIT_MQ_EVENT_ROUTING_KEY",    "scada.machine.event")

# ─── MySQL checkpoint store ────────────────────────────────────────────────
DATABASE_URL    = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/machine_telemetry?charset=utf8mb4",
)

# ─── Generator config ──────────────────────────────────────────────────────
N_MACHINES      = int(os.getenv("GEN_MACHINES",        "3"))
MASTER_SEED     = int(os.getenv("GEN_SEED",            "42"))
LIVE_INTERVAL_S = float(os.getenv("GEN_LIVE_INTERVAL", "3.0"))
DT              = float(os.getenv("GEN_DT_SECONDS",    "3.0"))
CHECKPOINT_EVERY= int(os.getenv("CHECKPOINT_EVERY",    "200"))

# Fast-forward: if a machine's checkpoint sim_ts is behind the newest
# timestamp already in machine_readings (e.g. resumed from a checkpoint
# older than the last backfill row), tick it with no sleep and without
# publishing/inserting each intermediate reading until it catches up —
# only failure/repair events are still published during catch-up, so
# machine_runs stays complete. Avoids waiting out the gap in real time.
FAST_FORWARD         = os.getenv("GEN_FAST_FORWARD", "1").strip() not in ("0", "false", "no")
FAST_FORWARD_CHECKPOINT_EVERY = int(os.getenv("GEN_FF_CHECKPOINT_EVERY", "20000"))

# ─── Engine ────────────────────────────────────────────────────────────────
_engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

_UPSERT_CHECKPOINT = text("""
    INSERT INTO generator_state (machine_id, state_json, saved_at)
    VALUES (:machine_id, :state_json, :saved_at)
    ON DUPLICATE KEY UPDATE
        state_json = VALUES(state_json),
        saved_at   = VALUES(saved_at)
""")

_SELECT_CHECKPOINT = text(
    "SELECT state_json FROM generator_state WHERE machine_id = :machine_id"
)

_CREATE_CHECKPOINT_TABLE = text("""
    CREATE TABLE IF NOT EXISTS generator_state (
        machine_id  INT  PRIMARY KEY,
        state_json  JSON NOT NULL,
        saved_at    DATETIME(3) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")


def _ensure_checkpoint_table() -> None:
    with _engine.begin() as conn:
        conn.execute(_CREATE_CHECKPOINT_TABLE)


def _load_checkpoint(machine_id: int) -> dict | None:
    with _engine.connect() as conn:
        row = conn.execute(_SELECT_CHECKPOINT, {"machine_id": machine_id}).fetchone()
    if row is None:
        return None
    raw = row[0]
    if isinstance(raw, str):
        return json.loads(raw)
    return raw  # already dict (some drivers deserialise JSON automatically)


def _save_checkpoint(gen: SyntheticMachineGenerator) -> None:
    with _engine.begin() as conn:
        conn.execute(_UPSERT_CHECKPOINT, {
            "machine_id": gen.machine_id,
            "state_json": json.dumps(gen.serialize()),
            "saved_at":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        })


# ─── RabbitMQ connection with retry ────────────────────────────────────────

def _connect_rabbitmq() -> tuple[pika.BlockingConnection, pika.channel.Channel]:
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    for attempt in range(1, 11):
        try:
            print(f"Connecting to RabbitMQ (attempt {attempt}/10)...")
            conn = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBIT_HOST, port=RABBIT_PORT, credentials=creds,
                    heartbeat=600, blocked_connection_timeout=300,
                )
            )
            ch = conn.channel()
            ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
            print("Connected to RabbitMQ.")
            return conn, ch
        except pika.exceptions.AMQPConnectionError:
            if attempt < 10:
                print(f"  Failed — retrying in 3s...")
                time.sleep(3)
            else:
                print("Max retries reached. Exiting.")
                sys.exit(1)


def _publish(ch, routing_key: str, payload: dict) -> None:
    ch.basic_publish(
        exchange=EXCHANGE,
        routing_key=routing_key,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2),
    )


# ─── Generator initialisation ──────────────────────────────────────────────

def _init_generators() -> list[SyntheticMachineGenerator]:
    generators = []
    for mid in range(N_MACHINES):
        seed = MASTER_SEED * 1000 + mid
        cp   = _load_checkpoint(mid)
        gen  = SyntheticMachineGenerator(machine_id=mid, seed=seed, dt=DT)
        if cp:
            try:
                gen.restore(cp)
                print(f"  Machine {mid+1}: resumed from checkpoint "
                      f"(seq={gen.seq}, state={gen.state})")
            except Exception as e:
                print(f"  Machine {mid+1}: checkpoint restore failed ({e}), starting fresh.")
        else:
            print(f"  Machine {mid+1}: no checkpoint — starting fresh "
                  f"(session={gen.session_id[:8]}…)")
        generators.append(gen)
    return generators


# ─── Fast-forward catch-up ─────────────────────────────────────────────────

def _fast_forward(generators: list[SyntheticMachineGenerator], ch) -> None:
    """Tick every machine whose sim_ts is behind wall-clock now, with no
    sleep between ticks, until each has caught all the way up to "now" —
    not just to the old backfill peak, so live streaming resumes exactly
    where a real-time clock would be.

    Readings are NOT published/inserted during catch-up (they'd just be
    duplicate/throwaway history at timestamps already in the past) — only
    failure/repair events are, so machine_runs stays complete. Each machine
    checkpoints periodically so a crash mid-catch-up can resume without
    starting over. The target is re-read each outer pass so a slow catch-up
    (many days behind) still lands within one tick of true "now" instead of
    a stale snapshot taken at the start.
    """
    target = datetime.now(timezone.utc)
    behind = [g for g in generators if g.sim_ts < target]
    if not behind:
        print(f"Fast-forward: all machines already caught up to now ({target}) "
              "— starting live.\n")
        return

    print(f"Fast-forward: catching up to wall-clock now ({target}) ...")
    for g in behind:
        gap = target - g.sim_ts
        print(f"  Machine {g.machine_id + 1}: {gap} behind (sim_ts={g.sim_ts})")

    t0 = time.time()
    total_ticks = 0
    ticks_since_checkpoint = {g.machine_id: 0 for g in behind}
    last_target_refresh = t0

    while behind and _running:
        # Re-read wall-clock now periodically (not every tick — that's the
        # one syscall worth avoiding in the hot loop) so machines that take
        # a while to catch up still converge on true "now", not a stale target.
        now_wall = time.time()
        if now_wall - last_target_refresh >= 1.0:
            target = datetime.now(timezone.utc)
            last_target_refresh = now_wall

        still_behind = []
        for gen in behind:
            gen.generate_one()  # advance state; discard the reading itself
            total_ticks += 1

            if gen._events:
                for evt in gen.pop_events():
                    try:
                        _publish(ch, ROUTING_EVENT, evt)
                    except pika.exceptions.AMQPError:
                        pass  # best-effort during catch-up; live loop retries future events

            mid = gen.machine_id
            ticks_since_checkpoint[mid] += 1
            if ticks_since_checkpoint[mid] >= FAST_FORWARD_CHECKPOINT_EVERY:
                _save_checkpoint(gen)
                ticks_since_checkpoint[mid] = 0

            if gen.sim_ts < target:
                still_behind.append(gen)
            else:
                _save_checkpoint(gen)
                print(f"  Machine {mid + 1}: caught up "
                      f"(seq={gen.seq}, sim_ts={gen.sim_ts})")
        behind = still_behind

    elapsed = time.time() - t0
    rate = total_ticks / elapsed if elapsed > 0 else 0.0
    print(f"Fast-forward complete: {total_ticks:,} ticks in {elapsed:.1f}s "
          f"({rate:,.0f} ticks/s) — starting live.\n")


# ─── Graceful shutdown ─────────────────────────────────────────────────────

_running = True


def _handle_shutdown(sig, frame):
    global _running
    print("\nShutdown signal received — checkpointing and exiting.")
    _running = False


signal.signal(signal.SIGINT,  _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)


# ─── Main loop ─────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\nPublisher starting — {N_MACHINES} machine(s), "
          f"interval={LIVE_INTERVAL_S}s, dt={DT}s\n")
    _ensure_checkpoint_table()
    conn, ch   = _connect_rabbitmq()
    generators = _init_generators()
    print()

    total_published = 0
    total_events    = 0

    try:
        if FAST_FORWARD:
            _fast_forward(generators, ch)

        while _running:
            tick_start = time.time()

            for gen in generators:
                if not _running:
                    break

                reading = gen.generate_one()
                try:
                    _publish(ch, ROUTING_DATA, reading)
                    total_published += 1
                except pika.exceptions.AMQPError:
                    print("RabbitMQ error — reconnecting...")
                    conn, ch = _connect_rabbitmq()
                    _publish(ch, ROUTING_DATA, reading)

                for evt in gen.pop_events():
                    try:
                        _publish(ch, ROUTING_EVENT, evt)
                        total_events += 1
                    except pika.exceptions.AMQPError:
                        conn, ch = _connect_rabbitmq()
                        _publish(ch, ROUTING_EVENT, evt)

                if gen.seq % CHECKPOINT_EVERY == 0 and gen.seq > 0:
                    _save_checkpoint(gen)

            if total_published % (100 * N_MACHINES) == 0 and total_published > 0:
                statuses = "  ".join(
                    f"M{g.machine_id+1}:{g.state[:4]}(seq={g.seq})" for g in generators
                )
                print(f"[{total_published:>7} readings | {total_events} events]  {statuses}")

            elapsed = time.time() - tick_start
            time.sleep(max(0.0, LIVE_INTERVAL_S - elapsed))

    finally:
        for gen in generators:
            try:
                _save_checkpoint(gen)
                print(f"  Checkpoint saved: Machine {gen.machine_id+1} seq={gen.seq}")
            except Exception as e:
                print(f"  Checkpoint failed for Machine {gen.machine_id+1}: {e}")
        try:
            conn.close()
        except Exception:
            pass
        _engine.dispose()
        print(f"Publisher stopped. Published {total_published} readings, {total_events} events.")


if __name__ == "__main__":
    main()
