"""MySQL connection for the ml/ package (independent of the backend)."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Single project-wide .env lives at the repo root, regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:root@localhost:3306/machine_telemetry?charset=utf8mb4",
)

_READING_COLS = (
    "session_id, seq, machine_name, state, ts, "
    "lot_1, lot_2, article, speed, length, lot_time_s, machine_time_s, "
    "steam_consumed_lot, water_consumed_lot, power_consumed_lot, air_consumed_lot, "
    "sf_flow, sf_tot, wat_flow, wat_tot, em_power, em_energy, "
    "vibration_rms, motor_current, bearing_temp, winding_temp, air_pressure, "
    "good_count, reject_count, truth_json"
)

# Columns to select when truth_json is not needed (serving / OEE / etc.)
_READING_COLS_NO_TRUTH = (
    "session_id, seq, machine_name, state, ts, "
    "lot_1, lot_2, article, speed, length, lot_time_s, machine_time_s, "
    "steam_consumed_lot, water_consumed_lot, power_consumed_lot, air_consumed_lot, "
    "sf_flow, sf_tot, wat_flow, wat_tot, em_power, em_energy, "
    "vibration_rms, motor_current, bearing_temp, winding_temp, air_pressure, "
    "good_count, reject_count"
)


def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)


def load_readings(
    engine=None,
    machine_name: str | None = None,
    include_truth: bool = True,
    chunksize: int = 200_000,
) -> pd.DataFrame:
    """Load readings for ONE machine in chunks to control peak memory.

    Parameters
    ----------
    machine_name  : required for tables with > 2M rows.
    include_truth : include truth_json column (needed for label fallback).
    chunksize     : rows per SQL fetch chunk (tune down if still OOM).
    """
    eng  = engine or get_engine()
    cols = _READING_COLS if include_truth else _READING_COLS_NO_TRUTH

    if machine_name:
        # No ORDER BY — Python sorts after loading (avoids MySQL temp-file sort)
        q = f"SELECT {cols} FROM machine_readings WHERE machine_name = :m"
        chunks = []
        with eng.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(
                text(q), {"m": machine_name}
            )
            col_names = list(result.keys())
            while True:
                rows = result.fetchmany(chunksize)
                if not rows:
                    break
                chunks.append(pd.DataFrame(rows, columns=col_names))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=col_names)
    else:
        with eng.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM machine_readings")).scalar()
        if n > 2_000_000:
            raise MemoryError(
                f"machine_readings has {n:,} rows — too large to load at once. "
                "Use iter_machines(engine) + load_readings(engine, machine_name=m) instead."
            )
        df = pd.read_sql_query(
            text(f"SELECT {cols} FROM machine_readings ORDER BY machine_name, ts, seq"),
            eng,
        )

    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None)
    return df


def load_readings_range(
    engine,
    machine_name: str,
    start_ts,
    end_ts,
    include_truth: bool = False,
    chunksize: int = 200_000,
) -> pd.DataFrame:
    """Load one machine's readings with ts in [start_ts, end_ts) in chunks."""
    cols = _READING_COLS if include_truth else _READING_COLS_NO_TRUTH
    q = (f"SELECT {cols} FROM machine_readings "
         "WHERE machine_name = :m AND ts >= :s AND ts < :e")
    params = {
        "m": machine_name,
        "s": pd.Timestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "e": pd.Timestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    }
    chunks = []
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(text(q), params)
        col_names = list(result.keys())
        while True:
            rows = result.fetchmany(chunksize)
            if not rows:
                break
            chunks.append(pd.DataFrame(rows, columns=col_names))
    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=col_names)
    if len(df):
        df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None)
    return df


def machine_ts_range(engine, machine_name: str) -> tuple:
    """(min_ts, max_ts) for one machine, or (None, None) if it has no rows."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MIN(ts), MAX(ts) FROM machine_readings WHERE machine_name = :m"),
            {"m": machine_name},
        ).fetchone()
    if row is None or row[0] is None:
        return None, None
    return (pd.Timestamp(row[0]).tz_localize(None),
            pd.Timestamp(row[1]).tz_localize(None))


def iter_machines(engine=None) -> list[str]:
    """Return sorted list of distinct machine_name values."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT machine_name FROM machine_readings ORDER BY machine_name")
        ).fetchall()
    return [r[0] for r in rows]


def ts_range(engine=None) -> tuple:
    """Return (global_min_ts, global_max_ts) as naive datetimes."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT MIN(ts), MAX(ts) FROM machine_readings")
        ).fetchone()
    import pandas as _pd
    return (
        _pd.Timestamp(row[0]).tz_localize(None),
        _pd.Timestamp(row[1]).tz_localize(None),
    )


def load_runs(engine=None) -> pd.DataFrame:
    """Load machine_runs failure events (rows with failure_ts populated)."""
    eng = engine or get_engine()
    q = text(
        "SELECT session_id, machine_name, component, severity, "
        "run_start_ts, failure_ts, repair_ts, run_hours_to_failure, seq_at_failure "
        "FROM machine_runs WHERE failure_ts IS NOT NULL "
        "ORDER BY machine_name, failure_ts"
    )
    df = pd.read_sql_query(q, eng)
    for col in ("run_start_ts", "failure_ts", "repair_ts"):
        df[col] = pd.to_datetime(df[col]).dt.tz_localize(None)
    return df
