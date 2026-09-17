"""Analytics + OEE, derived from machine_readings (MySQL / SQLAlchemy 2.0)."""
from datetime import timedelta

from sqlalchemy import case, func, select

from app.database import get_session, session_name_map, to_float, map_status
from app.models import Reading

# Lookback window in days per range key — bounds every analytics scan to the
# selected window instead of the whole table (mirrors oee_service).  Anchored
# to MAX(ts) in the data, not wall clock, so it works on backfilled data too.
_ANALYTICS_RANGE_DAYS = {
    "day":   1,
    "week":  7,
    "month": 30,
    "year":  365,
}
_MAX_LOTS = 40   # cap chart series length regardless of range

# For wide windows (month/year) MySQL's optimizer sometimes picks a full
# index scan (e.g. idx_reading_lot) over the ts range index, even though the
# range is far more selective — a known optimizer quirk on GROUP BY queries.
# Force the ts index for these ranges; day/week are already fast without it.
_FORCE_TS_INDEX_RANGES = {"month", "year"}


def _max_ts(session) -> "datetime | None":
    return session.execute(select(func.max(Reading.ts))).scalar()


def _maybe_force_ts_index(stmt, range: str):
    if range in _FORCE_TS_INDEX_RANGES:
        return stmt.with_hint(Reading, "FORCE INDEX (idx_reading_ts)")
    return stmt


# ── Speed vs Lot length (grouped by lot) ─────────────────────────────────────

def get_lot_analytics(range: str = "week"):
    """Most-recent lots' avg speed / max length, bounded to the selected window."""
    window_days = _ANALYTICS_RANGE_DAYS.get(range, _ANALYTICS_RANGE_DAYS["week"])

    with get_session() as session:
        max_ts = _max_ts(session)
        if max_ts is None:
            return []
        cutoff = max_ts - timedelta(days=window_days)

        stmt = (
            select(
                Reading.lot_1,
                func.avg(Reading.speed).label("avg_speed"),
                func.max(Reading.length).label("max_length"),
                func.max(Reading.ts).label("last_ts"),
            )
            .where(Reading.lot_1.is_not(None), Reading.ts >= cutoff)
            .group_by(Reading.lot_1)
            .order_by(func.max(Reading.ts).desc())
            .limit(_MAX_LOTS)
        )
        rows = session.execute(_maybe_force_ts_index(stmt, range)).all()

    out = [
        {
            "lot": str(row.lot_1),
            "speed": round(to_float(row.avg_speed), 1),
            "totalLength": round(to_float(row.max_length), 1),
        }
        for row in rows
    ]
    out.reverse()  # chronological order for the chart
    return out


# Legacy alias kept for /analytics/temperature route.
def get_temperature_analytics(range: str = "week"):
    return get_lot_analytics(range)


# ── Production rate vs target (per hour bucket) ───────────────────────────────

def get_production_analytics(range: str = "day"):
    """Hourly production rate, bounded to the selected window."""
    window_days = _ANALYTICS_RANGE_DAYS.get(range, _ANALYTICS_RANGE_DAYS["day"])

    with get_session() as session:
        max_ts = _max_ts(session)
        if max_ts is None:
            return []
        cutoff = max_ts - timedelta(days=window_days)

        stmt = (
            select(
                func.date_format(Reading.ts, "%m-%d %H:00").label("hour"),
                func.min(Reading.length).label("min_len"),
                func.max(Reading.length).label("max_len"),
            )
            .where(Reading.ts >= cutoff)
            .group_by(func.date_format(Reading.ts, "%m-%d %H:00"))
            .order_by(func.date_format(Reading.ts, "%m-%d %H:00"))
        )
        rows = session.execute(_maybe_force_ts_index(stmt, range)).all()

    result = [
        {"hour": row.hour, "rate": round(to_float(row.max_len) - to_float(row.min_len), 1)}
        for row in rows
    ]
    if result:
        avg_target = round(sum(r["rate"] for r in result) / len(result), 1)
        for r in result:
            r["target"] = avg_target
    return result


# ── Utilities consumption (totalizer deltas per session, summed) ───────────────

def get_utilities_analytics(range: str = "week"):
    """Utility consumption totals, bounded to sessions active in the window."""
    window_days = _ANALYTICS_RANGE_DAYS.get(range, _ANALYTICS_RANGE_DAYS["week"])

    with get_session() as session:
        max_ts = _max_ts(session)
        if max_ts is None:
            return [
                {"utility": u, "usage": 0.0, "cost": 0.0}
                for u in ("SF", "Water", "Air", "Power")
            ]
        cutoff = max_ts - timedelta(days=window_days)

        if range in _FORCE_TS_INDEX_RANGES:
            # Long windows (month/year): per-session grouping needs 800k+ random
            # row lookups for sf_tot/wat_tot (not covered by idx_reading_ts) and
            # gets very slow.  Approximate instead — per machine, (max − min) of
            # the totalizer within the window, summed.  Slightly undercounts
            # relative to true per-session deltas if multiple session resets
            # occurred inside the window, but is the accepted tradeoff for
            # fast long-range views (see PHASE3 plan, Part A.4 rollup is the
            # exact fix and can replace this later).
            per_machine_stmt = (
                select(
                    func.max(Reading.sf_tot).label("sf_max"),
                    func.min(Reading.sf_tot).label("sf_min"),
                    func.max(Reading.wat_tot).label("wat_max"),
                    func.min(Reading.wat_tot).label("wat_min"),
                )
                .where(Reading.ts >= cutoff)
                .group_by(Reading.machine_name)
                .with_hint(Reading, "FORCE INDEX (idx_reading_ts)")
            )
            per_machine = session.execute(per_machine_stmt).all()
            sf_total  = sum(max(to_float(r.sf_max) - to_float(r.sf_min), 0.0) for r in per_machine)
            wat_total = sum(max(to_float(r.wat_max) - to_float(r.wat_min), 0.0) for r in per_machine)
        else:
            # Totalizer resets each session → (max − min) per session = session
            # consumption.  Bound to rows in the window (ts >= cutoff,
            # index-backed), group per session, then sum in Python — avoids
            # SQLAlchemy's ambiguous select_from(subquery) cartesian-product trap.
            per_session_stmt = (
                select(
                    func.max(Reading.sf_tot).label("sf_tot"),
                    func.max(Reading.wat_tot).label("wat_tot"),
                )
                .where(Reading.ts >= cutoff)
                .group_by(Reading.session_id)
            )
            per_session = session.execute(per_session_stmt).all()
            sf_total  = sum(to_float(row.sf_tot)  for row in per_session)
            wat_total = sum(to_float(row.wat_tot) for row in per_session)

        air_stmt = select(func.sum(Reading.air_consumed_lot)).where(Reading.ts >= cutoff)
        power_stmt = select(func.sum(Reading.power_consumed_lot)).where(Reading.ts >= cutoff)
        if range in _FORCE_TS_INDEX_RANGES:
            air_stmt = air_stmt.with_hint(Reading, "FORCE INDEX (idx_reading_ts)")
            power_stmt = power_stmt.with_hint(Reading, "FORCE INDEX (idx_reading_ts)")

        air_total = session.scalar(air_stmt) or 0.0
        power_total = session.scalar(power_stmt) or 0.0

    return [
        {"utility": "SF",    "usage": round(to_float(sf_total),    3), "cost": 0.0},
        {"utility": "Water", "usage": round(to_float(wat_total),   3), "cost": 0.0},
        {"utility": "Air",   "usage": round(to_float(air_total),   3), "cost": 0.0},
        {"utility": "Power", "usage": round(to_float(power_total), 3), "cost": 0.0},
    ]


# ── OEE per machine ───────────────────────────────────────────────────────────

def get_oee_list():
    names = session_name_map()
    with get_session() as session:
        rows = session.execute(
            select(
                Reading.machine_name,
                func.count().label("total"),
                func.sum(
                    case((Reading.state == "running", 1), else_=0)
                ).label("running_count"),
                func.avg(
                    case((Reading.speed > 0, Reading.speed), else_=None)
                ).label("avg_speed"),
                func.max(Reading.speed).label("max_speed"),
            )
            .group_by(Reading.machine_name)
            .order_by(Reading.machine_name)
        ).all()

    out = []
    for row in rows:
        total = row.total or 1
        running = int(row.running_count or 0)
        avg_spd = to_float(row.avg_speed)
        max_spd = to_float(row.max_speed)

        availability = round(running / total * 100, 1)
        performance = round(avg_spd / max_spd * 100, 1) if max_spd else 0.0
        quality = 100.0
        oee = round(availability * performance * quality / 10_000, 1)

        out.append({
            "machine_id": row.machine_name,
            "machine_name": names.get(row.machine_name, row.machine_name),
            "availability": availability,
            "performance": performance,
            "quality": quality,
            "oee": oee,
        })
    return out
