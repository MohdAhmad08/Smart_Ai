"""OEE service — real pillars from machine_readings (MySQL / SQLAlchemy 2.0).

OEE = Availability × Performance × Quality

  Availability = running_time / (running + error + maintenance)
                 i.e. run-time fraction of planned production time.
                 idle/changeover are planned stops — excluded from denominator.

  Performance  = mean(speed | state=running) / NOMINAL_SPEED  [clamped 0-1]

  Quality      = Σ good_count / (Σ good_count + Σ reject_count)

OEE for a bucket = A × P × Q  (reported as %, each pillar also returned).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import case, func, select

import ml.config as ml_cfg
from app.database import get_session, map_status, session_name_map
from app.models import Reading

NOMINAL_SPEED = ml_cfg.NOMINAL_SPEED


def _oee_from_agg(running, downtime, total, avg_run_speed, good, reject) -> dict:
    """Compute OEE pillars from pre-aggregated counts.

    SQL SUM()/AVG() return decimal.Decimal under PyMySQL; coerce everything to
    float up front so the pillar arithmetic (Decimal * float) doesn't raise.

    Returns None ONLY when the machine has no readings at all in the window
    (nothing to show).  A machine with readings but no production time — e.g.
    all-idle during a weekend / off-shift — is a real, displayable state
    (0% availability → 0% OEE), not "no data", so it returns zeroed pillars
    rather than being dropped from the dashboard.
    """
    total    = int(total or 0)
    if total == 0:
        return None  # machine genuinely had no readings in the window

    running  = float(running  or 0)
    downtime = float(downtime or 0)

    prod_time = running + downtime
    if prod_time == 0:
        # Readings exist but all planned downtime (idle/changeover) — the
        # machine wasn't scheduled to produce. Availability/OEE are 0.
        return {
            "availability": 0.0,
            "performance":  0.0,
            "quality":      0.0,
            "oee":          0.0,
        }

    availability  = running / prod_time
    run_spd       = float(avg_run_speed or 0)
    performance   = min(run_spd / NOMINAL_SPEED, 1.0) if NOMINAL_SPEED > 0 else 0.0
    g, r          = float(good or 0), float(reject or 0)
    quality       = g / (g + r) if (g + r) > 0 else 1.0

    oee = round(availability * performance * quality * 100, 2)
    return {
        "availability": round(availability * 100, 2),
        "performance":  round(performance  * 100, 2),
        "quality":      round(quality      * 100, 2),
        "oee":          oee,
    }


# ── Snapshot (recent window per machine) ─────────────────────────────────────

def get_oee_snapshot(window_days: int = 7) -> list[dict]:
    """Return one OEE summary row per physical machine over a recent window.

    "Current" OEE should reflect recent operation, not a lifetime average, so
    we bound the scan to the last `window_days` (anchored to the latest reading
    timestamp, not wall clock — works on historical/backfilled data).  This also
    keeps the GROUP BY fast instead of scanning all of machine_readings.
    """
    names = session_name_map()

    with get_session() as session:
        max_ts = session.execute(select(func.max(Reading.ts))).scalar()
        if max_ts is None:
            return []
        cutoff = max_ts - timedelta(days=window_days)

        rows = session.execute(
            select(
                Reading.machine_name,
                func.sum(case((Reading.state == "running", 1), else_=0)).label("running"),
                func.sum(
                    case((Reading.state.in_(["error", "maintenance"]), 1), else_=0)
                ).label("downtime"),
                func.count().label("total"),
                func.avg(
                    case((Reading.state == "running", Reading.speed), else_=None)
                ).label("avg_run_speed"),
                func.sum(Reading.good_count).label("good"),
                func.sum(Reading.reject_count).label("reject"),
            )
            .where(Reading.ts >= cutoff)
            .group_by(Reading.machine_name)
            .order_by(Reading.machine_name)
        ).all()

    out = []
    for row in rows:
        pillars = _oee_from_agg(
            row.running, row.downtime, row.total,
            row.avg_run_speed, row.good, row.reject,
        )
        if pillars is None:
            continue
        out.append({
            "machine_id":   row.machine_name,
            "machine_name": names.get(row.machine_name, row.machine_name),
            **pillars,
        })
    return out


# ── Timeseries (per bucket) ──────────────────────────────────────────────────

# Each preset = (MySQL date_format for the bucket, lookback window in days).
# Window bounds the scan and keeps the point count chart-friendly.
_RANGE_PRESETS = {
    "day":   ("%Y-%m-%d %H:00", 1),     # last 24 h, hourly buckets
    "week":  ("%Y-%m-%d %H:00", 7),     # last 7 d, hourly buckets
    "month": ("%Y-%m-%d",       30),    # last 30 d, daily buckets
    "year":  ("%Y-%m-%d",       365),   # last 365 d, daily buckets
}


def get_oee_timeseries(
    machine: str | None = None,
    range: str = "week",
) -> list[dict]:
    """Return OEE bucketed over a bounded time window for charting.

    Parameters
    ----------
    machine : machine_name filter (None → all machines).
    range   : 'day' | 'week' | 'month' | 'year'.  Selects both the bucket
              granularity and the lookback window (see _RANGE_PRESETS).

    The window is measured back from the latest reading timestamp (not wall
    clock), so it works correctly on historical/backfilled data.
    """
    fmt, window_days = _RANGE_PRESETS.get(range, _RANGE_PRESETS["week"])
    names = session_name_map()

    with get_session() as session:
        # Anchor the window to the data's max ts, not datetime.now()
        max_ts = session.execute(select(func.max(Reading.ts))).scalar()
        if max_ts is None:
            return []
        cutoff = max_ts - timedelta(days=window_days)

        stmt = select(
            Reading.machine_name,
            func.date_format(Reading.ts, fmt).label("bucket"),
            func.sum(case((Reading.state == "running", 1), else_=0)).label("running"),
            func.sum(
                case((Reading.state.in_(["error", "maintenance"]), 1), else_=0)
            ).label("downtime"),
            func.count().label("total"),
            func.avg(
                case((Reading.state == "running", Reading.speed), else_=None)
            ).label("avg_run_speed"),
            func.sum(Reading.good_count).label("good"),
            func.sum(Reading.reject_count).label("reject"),
        ).where(Reading.ts >= cutoff)

        if machine:
            stmt = stmt.where(Reading.machine_name == machine)

        stmt = stmt.group_by(
            Reading.machine_name,
            func.date_format(Reading.ts, fmt),
        ).order_by(Reading.machine_name, "bucket")

        rows = session.execute(stmt).all()

    out = []
    for row in rows:
        pillars = _oee_from_agg(
            row.running, row.downtime, row.total,
            row.avg_run_speed, row.good, row.reject,
        )
        if pillars is None:
            continue
        out.append({
            "machine_name": names.get(row.machine_name, row.machine_name),
            "time":         row.bucket,
            **pillars,
        })
    return out
