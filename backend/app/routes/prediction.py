from fastapi import APIRouter
from app.services.prediction_service import (
    predict_machine,
    predict_all,
    current_model_summary,
)
from app.services.model_health_service import get_model_health, get_registry

router = APIRouter()


@router.get("/predict/{machine}")
def predict(machine: str):
    """Score one machine by machine_name. Returns predicted component + probabilities."""
    return predict_machine(machine)


@router.get("/maintenance")
def maintenance():
    """Score all machines, sorted by risk (highest first)."""
    return predict_all()


@router.get("/model/info")
def model_info():
    """Summary of the currently loaded model artifact."""
    return current_model_summary()


@router.get("/model/health")
def model_health():
    """Model-health panel: production version, live feedback metrics, drift status."""
    return get_model_health()


@router.get("/model/registry")
def model_registry():
    """Model version history from the registry (newest first)."""
    return get_registry()
