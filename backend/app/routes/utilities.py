from fastapi import APIRouter
from app.services.utilities_service import get_utilities

router = APIRouter()

@router.get("/utilities")
def utilities():
    return get_utilities()