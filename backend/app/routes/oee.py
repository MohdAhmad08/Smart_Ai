from fastapi import APIRouter, Query
from app.services.oee_service import get_oee_snapshot, get_oee_timeseries

router = APIRouter()


@router.get("/oee")
def oee():
    """OEE snapshot — one row per machine over its full history."""
    return get_oee_snapshot()


@router.get("/oee/timeseries")
def oee_timeseries(
    machine: str | None = Query(None, description="machine_name filter"),
    range:   str        = Query("week", description="day|week|month|year"),
):
    """OEE bucketed over a bounded time window for trend charts."""
    return get_oee_timeseries(machine, range)
