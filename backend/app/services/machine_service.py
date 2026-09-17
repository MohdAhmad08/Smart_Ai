"""Machine cards and status timeline (MySQL / SQLAlchemy 2.0)."""
from datetime import timedelta

from sqlalchemy import case, func, select

from app.database import get_session, session_name_map, to_float, hms_to_minutes, map_status
from app.models import Reading


def get_machine_data():
    """One card per physical machine, built from its latest reading."""
    names = session_name_map()

    with get_session() as session:
        machine_names = session.scalars(
            select(Reading.machine_name).distinct().order_by(Reading.machine_name)
        ).all()

        out = []
        for mname in machine_names:
            r = session.scalars(
                select(Reading)
                .where(Reading.machine_name == mname)
                .order_by(Reading.ts.desc())
                .limit(1)
            ).first()
            if r is None:
                continue
            out.append({
                "id": mname,
                "name": names.get(mname, mname),
                "lot1": str(r.lot_1 or ""),
                "lot2": str(r.lot_2 or ""),
                "articleNumber": str(r.article or ""),
                "totalLength": to_float(r.length),
                "status": map_status(r.state),
                "lotTime": hms_to_minutes(r.lot_time_s),
                "machineRunningTime": hms_to_minutes(r.machine_time_s),
                "speed": to_float(r.speed),
            })
    return out


# Each preset = (MySQL date_format for the bucket, lookback window in days).
# Window bounds the scan to the selected range instead of the whole table —
# mirrors oee_service._RANGE_PRESETS.
_TIMELINE_RANGE_PRESETS = {
    "shift": ("%H:%i", 1 / 3),   # last 8 h, per-minute-ish buckets (~5 min via HH:MM)
    "day":   ("%H:00", 1),       # last 24 h, hourly buckets
    "week":  ("%m-%d", 7),       # last 7 d, daily buckets
    "month": ("%m-%d", 30),      # last 30 d, daily buckets
}

# MySQL's optimizer occasionally skips the ts range index on wide GROUP BY
# windows (see analytics_service._FORCE_TS_INDEX_RANGES); force it for month.
_FORCE_TS_INDEX_RANGES = {"month"}


def get_machine_timeline(range: str = "shift"):
    """Bucket readings into running/stopped counts, bounded to the selected range.

    The window is anchored to MAX(ts) in the data (not wall clock) so it works
    correctly on backfilled/historical data, and it bounds the scan to just the
    selected range instead of the entire machine_readings table.
    """
    fmt, window_days = _TIMELINE_RANGE_PRESETS.get(range, _TIMELINE_RANGE_PRESETS["shift"])

    with get_session() as session:
        max_ts = session.execute(select(func.max(Reading.ts))).scalar()
        if max_ts is None:
            return []
        cutoff = max_ts - timedelta(days=window_days)

        stmt = (
            select(
                func.date_format(Reading.ts, fmt).label("bucket"),
                func.sum(case((Reading.state == "running", 1), else_=0)).label("running"),
                func.sum(case((Reading.state != "running", 1), else_=0)).label("stopped"),
            )
            .where(Reading.ts >= cutoff)
            .group_by(func.date_format(Reading.ts, fmt))
            .order_by(func.date_format(Reading.ts, fmt))
        )
        if range in _FORCE_TS_INDEX_RANGES:
            stmt = stmt.with_hint(Reading, "FORCE INDEX (idx_ts_state)")
        rows = session.execute(stmt).all()

    return [
        {"time": row.bucket, "running": int(row.running or 0), "stopped": int(row.stopped or 0)}
        for row in rows
    ]
