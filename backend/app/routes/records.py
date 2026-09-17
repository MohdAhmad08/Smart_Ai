from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.services.records_service import get_records_page, stream_records_csv

router = APIRouter()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/database-records")
def records(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    machine: str | None = Query(None),
    status: str | None = Query(None),
    start: str | None = Query(None, description="ISO date/datetime, inclusive"),
    end: str | None = Query(None, description="ISO date/datetime, inclusive"),
    search: str | None = Query(None),
):
    """Paginated, server-filtered records. Only `page_size` rows are ever
    materialized — never load the whole table into memory or the browser."""
    return get_records_page(
        page=page, page_size=page_size, machine=machine, status=status,
        start=_parse_dt(start), end=_parse_dt(end), search=search,
    )


@router.get("/database-records/export")
def records_export(
    machine: str | None = Query(None),
    status: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    search: str | None = Query(None),
):
    """Stream a CSV of every row matching the active filters (no page cap)."""
    filename = f"jeans-production-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        stream_records_csv(
            machine=machine, status=status,
            start=_parse_dt(start), end=_parse_dt(end), search=search,
        ),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
