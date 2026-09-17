"""Alerts inferred from the latest reading of each machine (MySQL / SQLAlchemy 2.0)."""
from sqlalchemy import select

from app.database import get_session, session_name_map, map_status, to_float
from app.models import Reading


def get_alerts():
    names = session_name_map()
    alerts = []
    counter = 0

    with get_session() as session:
        machine_names = session.scalars(
            select(Reading.machine_name).distinct().order_by(Reading.machine_name)
        ).all()

        for mname in machine_names:
            r = session.scalars(
                select(Reading)
                .where(Reading.machine_name == mname)
                .order_by(Reading.ts.desc())
                .limit(1)
            ).first()
            if r is None:
                continue

            name = names.get(mname, mname)
            ts = r.ts.isoformat() if r.ts else None
            status = map_status(r.state)

            if status != "running":
                counter += 1
                alerts.append({
                    "id": f"alert-{counter}",
                    "timestamp": ts,
                    "type": f"{name} Not Running",
                    "message": f"{name} is currently in '{status}' state.",
                    "severity": "warning",
                    "iconName": "Activity",
                })

            if r.em_power is None:
                counter += 1
                alerts.append({
                    "id": f"alert-{counter}",
                    "timestamp": ts,
                    "type": "Power Metering Offline",
                    "message": f"{name}: EM power meter is not reporting a value.",
                    "severity": "warning",
                    "iconName": "AlertTriangle",
                })

            if status == "running" and to_float(r.sf_flow) == 0:
                counter += 1
                alerts.append({
                    "id": f"alert-{counter}",
                    "timestamp": ts,
                    "type": "No Steam Flow",
                    "message": f"{name} is running with zero SF flow.",
                    "severity": "info",
                    "iconName": "ThermometerSun",
                })

    return alerts
