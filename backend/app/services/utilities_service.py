"""Utility gauge cards, built from the most recent reading (MySQL / SQLAlchemy 2.0)."""
from sqlalchemy import select

from app.database import get_session, to_float
from app.models import Reading


def get_utilities():
    with get_session() as session:
        r = session.scalars(
            select(Reading).order_by(Reading.ts.desc()).limit(1)
        ).first()

    if r is None:
        return []

    return [
        {
            "id": "SF",
            "name": "SF Flowrate",
            "type": "sf",
            "processValue": to_float(r.sf_flow),
            "processUnit": "m³/h",
            "totalizer": to_float(r.sf_tot),
            "totalizerUnit": "m³",
            "lotConsumption": to_float(r.steam_consumed_lot),
            "lotConsumptionUnit": "/lot",
            "status": "normal",
        },
        {
            "id": "WATER",
            "name": "Water Flowrate",
            "type": "water",
            "processValue": to_float(r.wat_flow),
            "processUnit": "m³/h",
            "totalizer": to_float(r.wat_tot),
            "totalizerUnit": "m³",
            "lotConsumption": to_float(r.water_consumed_lot),
            "lotConsumptionUnit": "/lot",
            "status": "normal",
        },
        {
            "id": "AIR",
            "name": "Air Flowrate",
            "type": "air",
            "processValue": 0.0,
            "processUnit": "Nm³/h",
            "totalizer": 0.0,
            "totalizerUnit": "Nm³",
            "lotConsumption": to_float(r.air_consumed_lot),
            "lotConsumptionUnit": "/lot",
            "status": "normal",
        },
        {
            "id": "POWER",
            "name": "EM Power",
            "type": "power",
            "processValue": to_float(r.em_power),
            "processUnit": "kW",
            "totalizer": to_float(r.em_energy),
            "totalizerUnit": "kWh",
            "lotConsumption": to_float(r.power_consumed_lot),
            "lotConsumptionUnit": "kWh/lot",
            "energy": to_float(r.em_energy),
            "energyUnit": "kWh",
            "status": "normal",
        },
    ]
