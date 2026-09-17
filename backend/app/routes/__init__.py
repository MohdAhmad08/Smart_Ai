# app/routes/__init__.py
"""
Expose route submodules as attributes of app.routes.
This lets `from app.routes import machine` work reliably.
"""
__all__ = ["machine", "analytics", "utilities", "alerts", "records"]

# import submodules so package-level import finds them
from . import machine, analytics, utilities, alerts, records