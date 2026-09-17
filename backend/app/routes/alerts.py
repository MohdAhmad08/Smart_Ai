from fastapi import APIRouter
from app.services.alerts_service import get_alerts

router = APIRouter()

@router.get("/alerts")
def alerts():
    return get_alerts()

a=2