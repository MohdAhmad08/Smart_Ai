from fastapi import APIRouter, Query
from app.services.machine_service import get_machine_data, get_machine_timeline

router = APIRouter()

@router.get("/machine-data")
def machine_data():
    return get_machine_data()

@router.get("/machine-timeline")
def timeline(range: str = Query("shift")):
    return get_machine_timeline(range)
