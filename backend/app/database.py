"""MySQL access layer + shared parsing helpers (SQLAlchemy 2.0).

All backend data lives in the `machine_telemetry` MySQL database.
See app/models.py for ORM definitions and app/config.py for DATABASE_URL.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL
from app.models import Base, Reading

_engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal: sessionmaker[Session] = sessionmaker(bind=_engine, expire_on_commit=False)


def create_tables() -> None:
    """Create all tables if they don't exist yet (idempotent)."""
    Base.metadata.create_all(_engine)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Parsing helpers (same API as the old Mongo version) ──────────────────────

def to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def hms_to_minutes(value) -> int:
    """Accept either an integer seconds value (stored in DB) or an 'H:M:S' string."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value) // 60
    try:
        nums = [int(p) for p in str(value).split(":")]
    except ValueError:
        return 0
    while len(nums) < 3:
        nums.insert(0, 0)
    h, m, s = nums[0], nums[1], nums[2]
    return int(h * 60 + m + round(s / 60))


def parse_timestamp(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


_VALID_STATUS = {"running", "idle", "maintenance", "error", "changeover"}


def map_status(state) -> str:
    s = str(state or "").lower()
    return s if s in _VALID_STATUS else "idle"


def session_name_map() -> dict[str, str]:
    """Map each machine_name to a stable display label.

    Ordering by DISTINCT machine_name (index-backed) instead of MIN(ts) — the
    latter forced a full-table aggregate + temp sort over all of machine_readings
    (~30 s on 5 M rows).  machine_name is already the display label, so a plain
    distinct/ordered scan of the index is all that's needed.
    """
    with get_session() as session:
        rows = session.execute(
            select(Reading.machine_name)
            .distinct()
            .order_by(Reading.machine_name)
        ).all()
    return {row.machine_name: row.machine_name for row in rows}
