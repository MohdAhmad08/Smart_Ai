"""Idempotent DDL for the Plan 03 lifecycle tables (ml-package side).

The backend ORM (backend/app/models.py) defines the same tables for
Base.metadata.create_all; ml/ keeps its own CREATE TABLE IF NOT EXISTS so the
scheduler / retention / drift jobs can run without importing the backend.
Schemas must stay in sync with the ORM definitions.
"""
from __future__ import annotations

from sqlalchemy import text

_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS feature_snapshots (
        id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        pipeline_version VARCHAR(64)  NOT NULL,
        machine_name     VARCHAR(64)  NOT NULL DEFAULT '',
        shard_path       VARCHAR(512) NOT NULL,
        range_start_ts   DATETIME(3)  NOT NULL,
        range_end_ts     DATETIME(3)  NOT NULL,
        row_count        INT          NOT NULL,
        class_counts     JSON         NOT NULL,
        ref_dist         JSON         NULL,
        created_at       DATETIME(3)  NOT NULL,
        KEY idx_snap_version (pipeline_version),
        KEY idx_snap_range   (range_start_ts, range_end_ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS predictions (
        id              BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
        ts              DATETIME(3) NOT NULL,
        session_id      VARCHAR(36) NULL,
        seq             INT         NULL,
        machine_name    VARCHAR(64) NOT NULL,
        predicted_class VARCHAR(32) NOT NULL,
        probabilities   JSON        NULL,
        model_version   VARCHAR(64) NULL,
        KEY idx_pred_ts      (ts),
        KEY idx_pred_machine (machine_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS drift_metrics (
        id            BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
        ts            DATETIME(3) NOT NULL,
        feature       VARCHAR(64) NOT NULL,
        psi           DOUBLE      NULL,
        ks_p          DOUBLE      NULL,
        flag          VARCHAR(16) NOT NULL DEFAULT 'stable',
        model_version VARCHAR(64) NULL,
        KEY idx_drift_ts (ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS model_registry (
        id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        version          VARCHAR(64)  NOT NULL UNIQUE,
        stage            VARCHAR(32)  NOT NULL DEFAULT 'Staging',
        pipeline_version VARCHAR(64)  NULL,
        metrics          JSON         NULL,
        mlflow_run_id    VARCHAR(64)  NULL,
        artifact_path    VARCHAR(512) NULL,
        trained_at       DATETIME(3)  NULL,
        promoted_at      DATETIME(3)  NULL,
        KEY idx_registry_stage (stage)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS live_metrics (
        id                 BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
        ts                 DATETIME(3) NOT NULL,
        window_days        INT         NOT NULL,
        class_name         VARCHAR(32) NOT NULL,
        precision_score    DOUBLE      NULL,
        recall_score       DOUBLE      NULL,
        lead_time_median_h DOUBLE      NULL,
        n_predictions      INT         NOT NULL DEFAULT 0,
        n_failures         INT         NOT NULL DEFAULT 0,
        model_version      VARCHAR(64) NULL,
        KEY idx_live_ts (ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def ensure_tables(engine) -> None:
    """Create every lifecycle table that doesn't exist yet."""
    with engine.begin() as conn:
        for ddl in _DDL:
            conn.execute(text(ddl))
