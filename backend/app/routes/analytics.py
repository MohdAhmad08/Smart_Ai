from fastapi import APIRouter, Query
from app.services.analytics_service import (
    get_lot_analytics,
    get_temperature_analytics,
    get_production_analytics,
    get_utilities_analytics,
)

router = APIRouter()

@router.get("/analytics/lot")
def lot(range: str = Query("week", description="day|week|month|year")):
    return get_lot_analytics(range)

@router.get("/analytics/temperature")
def temperature(range: str = Query("week", description="day|week|month|year")):
    return get_temperature_analytics(range)

@router.get("/analytics/production")
def production(range: str = Query("day", description="day|week|month|year")):
    return get_production_analytics(range)

@router.get("/analytics/utilities")
def utilities(range: str = Query("week", description="day|week|month|year")):
    return get_utilities_analytics(range)
# /api/oee is now handled by app.routes.oee (oee_service.py)
