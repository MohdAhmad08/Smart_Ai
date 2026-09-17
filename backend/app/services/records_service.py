"""Database table rows — paginated, server-filtered (MySQL / SQLAlchemy 2.0).

Previously loaded up to 5,000 full rows and filtered them in Python; now every
filter (machine, status, date range, search) is pushed into SQL and only the
current page is materialized, so the response stays small regardless of how
many rows machine_readings holds.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Iterator

from sqlalchemy import func, select, or_, String

from app.database import get_session, session_name_map, to_float, hms_to_minutes, map_status
from app.models import Reading

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _search_clause(search: str):
    like = f"%{search}%"
    return or_(
        func.cast(Reading.lot_1, String).like(like),
        func.cast(Reading.lot_2, String).like(like),
        Reading.article.like(like),
        Reading.machine_name.like(like),
    )


def _estimate_total_rows(session) -> int:
    """Fast approximate row count from InnoDB table statistics — used only
    for the unfiltered case (no WHERE clause) where an exact COUNT(*) would
    otherwise scan the full index (~3s at 5M+ rows) just to render a page
    count.  Filtered counts stay exact since the filters already bound them."""
    from sqlalchemy import text
    n = session.execute(text(
        "SELECT TABLE_ROWS FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'machine_readings'"
    )).scalar()
    return int(n or 0)


def _to_record(r: Reading, names: dict[str, str]) -> dict:
    return {
        "id": str(r.id),
        "timestamp": r.ts.isoformat() if r.ts else None,
        "machineId": names.get(r.machine_name, r.machine_name),
        "lot1": str(r.lot_1 or ""),
        "lot2": str(r.lot_2 or ""),
        "articleNumber": str(r.article or ""),
        "totalLength": to_float(r.length),
        "speed": to_float(r.speed),
        "lotTime": hms_to_minutes(r.lot_time_s),
        "machineRunningTime": hms_to_minutes(r.machine_time_s),
        "sfConsumption": to_float(r.steam_consumed_lot),
        "waterConsumption": to_float(r.water_consumed_lot),
        "airConsumption": to_float(r.air_consumed_lot),
        "gasConsumption": 0.0,
        "powerConsumption": to_float(r.power_consumed_lot),
        "status": map_status(r.state),
    }


def get_records_page(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    machine: str | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    search: str | None = None,
) -> dict:
    """Return one page of records plus pagination metadata.

    All filters run in SQL; only `page_size` rows are ever materialized.
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    names = session_name_map()

    where_clauses = []
    if machine:
        where_clauses.append(Reading.machine_name == machine)
    if status and status != "all":
        where_clauses.append(Reading.state == status)
    if start:
        where_clauses.append(Reading.ts >= start)
    if end:
        where_clauses.append(Reading.ts <= end)
    if search:
        where_clauses.append(_search_clause(search))

    with get_session() as session:
        if where_clauses:
            count_stmt = select(func.count()).select_from(Reading)
            for c in where_clauses:
                count_stmt = count_stmt.where(c)
            total = session.execute(count_stmt).scalar() or 0
        else:
            total = _estimate_total_rows(session)

        stmt = select(Reading).order_by(Reading.ts.desc())
        for c in where_clauses:
            stmt = stmt.where(c)
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)

        readings = session.scalars(stmt).all()

    rows = [_to_record(r, names) for r in readings]
    pages = max((total + page_size - 1) // page_size, 1)

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


# ── Streaming CSV export (respects the same filters, no row cap) ─────────────

_CSV_HEADERS = [
    "ID", "Timestamp", "Machine", "Lot 1", "Lot 2", "Article",
    "Length (m)", "Speed (m/min)", "Lot Time (min)", "Run Time (min)",
    "SF (m3)", "Water (L)", "Air (Nm3)", "Gas (m3)", "Power (kWh)", "Status",
]

_EXPORT_CHUNK = 2_000


def stream_records_csv(
    machine: str | None = None,
    status: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    search: str | None = None,
) -> Iterator[str]:
    """Yield CSV text in chunks — streams straight from MySQL, never buffers
    the whole filtered result set in memory."""
    names = session_name_map()

    where_clauses = []
    if machine:
        where_clauses.append(Reading.machine_name == machine)
    if status and status != "all":
        where_clauses.append(Reading.state == status)
    if start:
        where_clauses.append(Reading.ts >= start)
    if end:
        where_clauses.append(Reading.ts <= end)
    if search:
        where_clauses.append(_search_clause(search))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_HEADERS)
    yield buf.getvalue()
    buf.seek(0); buf.truncate(0)

    with get_session() as session:
        stmt = select(Reading).order_by(Reading.ts.desc())
        for c in where_clauses:
            stmt = stmt.where(c)

        result = session.execute(
            stmt.execution_options(yield_per=_EXPORT_CHUNK)
        )
        n = 0
        for (r,) in result:
            rec = _to_record(r, names)
            writer.writerow([
                rec["id"], rec["timestamp"], rec["machineId"], rec["lot1"], rec["lot2"],
                rec["articleNumber"], rec["totalLength"], rec["speed"], rec["lotTime"],
                rec["machineRunningTime"], rec["sfConsumption"], rec["waterConsumption"],
                rec["airConsumption"], rec["gasConsumption"], rec["powerConsumption"],
                rec["status"],
            ])
            n += 1
            if n % _EXPORT_CHUNK == 0:
                yield buf.getvalue()
                buf.seek(0); buf.truncate(0)

    tail = buf.getvalue()
    if tail:
        yield tail
