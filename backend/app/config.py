from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── Project root → sys.path so `import ml` works from anywhere ──────────────
_PROJECT_ROOT_PATH = Path(__file__).resolve().parent.parent.parent  # d:\Ali Stuff\Taha_fyp
_PROJECT_ROOT = str(_PROJECT_ROOT_PATH)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Single project-wide .env lives at the repo root, regardless of cwd.
load_dotenv(_PROJECT_ROOT_PATH / ".env")


class Settings:
    PROJECT_NAME: str = "Manufacturing Dashboard API"
    VERSION: str = "0.2"
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:root@localhost:3306/machine_telemetry?charset=utf8mb4",
    )


settings = Settings()

# Top-level alias consumed by database.py
DATABASE_URL: str = settings.DATABASE_URL
