"""Live prediction service — loads the trained model artifact and scores each machine.

The feature engineering is IDENTICAL to training (imported from ml/features.py)
to prevent train/serve skew.  The model is cached in-process and reloaded
whenever metadata.json changes on disk.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select

from app.database import get_session
from app.models import Reading

# ── Path to the ml/ package ─────────────────────────────────────────────────
# config.py already added the project root to sys.path, so `import ml` works.
import ml.config as ml_cfg
from ml.evaluate import apply_thresholds
from ml.features import build_features_for_machine, get_feature_columns

# ── Artifact paths ───────────────────────────────────────────────────────────
_MODEL_PATH    = ml_cfg.ARTIFACTS_DIR / "model.json"
_META_PATH     = ml_cfg.ARTIFACTS_DIR / "metadata.json"

# ── Model cache ──────────────────────────────────────────────────────────────
_model         = None
_meta: dict    = {}
_feat_cols: list[str] = []
_class_names: list[str] = ml_cfg.CLASS_NAMES
_meta_mtime: float = 0.0
_model_version: str = ""
_registry_checked_at: float = 0.0
_REGISTRY_TTL_S = 30.0   # re-query the registry pointer at most this often


def _load_from_bundle(model_path: Path, meta_path: Path, version: str) -> bool:
    global _model, _meta, _feat_cols, _class_names, _meta_mtime, _model_version
    try:
        from xgboost import XGBClassifier
    except ImportError:
        return False
    try:
        m = XGBClassifier()
        m.load_model(str(model_path))
        with open(meta_path) as f:
            meta = json.load(f)

        _model         = m
        _meta          = meta
        _feat_cols     = meta.get("feature_columns", get_feature_columns(ml_cfg))
        _class_names   = meta.get("class_names", ml_cfg.CLASS_NAMES)
        _meta_mtime    = meta_path.stat().st_mtime
        _model_version = version
        print(f"[prediction_service] loaded model {version} from {model_path.parent}")
        return True
    except Exception as e:
        print(f"[prediction_service] Failed to load model: {e}")
        return False


def _load_model() -> bool:
    """Load the Production model from the registry pointer (Plan 03 Part F);
    fall back to the local ml/artifacts bundle when no registry row exists.
    Reloads automatically when the registry version or bundle file changes."""
    global _registry_checked_at
    import time as _time

    now = _time.monotonic()
    if _model is not None and (now - _registry_checked_at) < _REGISTRY_TTL_S:
        return True
    _registry_checked_at = now

    # 1. Registry pointer (MySQL model_registry → ml/model_store/<version>/)
    try:
        from ml.registry import production_row
        row = production_row()
    except Exception:
        row = None

    if row is not None:
        bundle  = Path(row["artifact_path"])
        model_p = bundle / "model.json"
        meta_p  = bundle / "metadata.json"
        if model_p.exists() and meta_p.exists():
            if (_model is not None and _model_version == row["version"]
                    and meta_p.stat().st_mtime == _meta_mtime):
                return True
            if _load_from_bundle(model_p, meta_p, row["version"]):
                return True

    # 2. Fallback: local artifacts (pre-registry installs)
    if not _MODEL_PATH.exists() or not _META_PATH.exists():
        return _model is not None
    if (_model is not None and _model_version == ""
            and _META_PATH.stat().st_mtime == _meta_mtime):
        return True
    return _load_from_bundle(_MODEL_PATH, _META_PATH, "")


# ── Reading → DataFrame conversion ───────────────────────────────────────────

def _readings_to_df(readings: list) -> pd.DataFrame:
    """Convert a list of ORM Reading objects to a flat DataFrame."""
    rows = []
    for r in readings:
        rows.append({
            "session_id":    r.session_id,
            "seq":           r.seq,
            "machine_name":  r.machine_name,
            "state":         r.state,
            "ts":            r.ts,
            "lot_1":         r.lot_1,
            "lot_2":         r.lot_2,
            "speed":         r.speed,
            "length":        r.length,
            "lot_time_s":    r.lot_time_s,
            "machine_time_s": r.machine_time_s,
            "steam_consumed_lot": r.steam_consumed_lot,
            "water_consumed_lot": r.water_consumed_lot,
            "sf_flow":       r.sf_flow,
            "sf_tot":        r.sf_tot,
            "wat_flow":      r.wat_flow,
            "wat_tot":       r.wat_tot,
            "em_power":      r.em_power,
            "em_energy":     r.em_energy,
            "vibration_rms": r.vibration_rms,
            "motor_current": r.motor_current,
            "bearing_temp":  r.bearing_temp,
            "winding_temp":  r.winding_temp,
            "air_pressure":  r.air_pressure,
            "good_count":    r.good_count,
            "reject_count":  r.reject_count,
        })
    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None)
    return df


# ── Core scoring function ─────────────────────────────────────────────────────

def predict_machine(machine_name: str) -> dict:
    """Score the current state of one machine.

    Returns a dict with predicted_class, probabilities, risk_score, and metadata.
    """
    model_ready = _load_model()

    # Load the latest MAX_WINDOW + buffer readings (sorted ascending)
    n_load = ml_cfg.MAX_WINDOW + 20
    with get_session() as session:
        readings = list(session.scalars(
            select(Reading)
            .where(Reading.machine_name == machine_name)
            .order_by(Reading.ts.desc())
            .limit(n_load)
        ).all())

    if len(readings) < 5:
        return {
            "machine_name":    machine_name,
            "predicted_class": "insufficient_data",
            "probabilities":   {},
            "risk_score":      0.0,
            "model_version":   _meta.get("pipeline_version", "none"),
            "ts":              datetime.now(timezone.utc).isoformat(),
            "note":            f"Only {len(readings)} readings available (need ≥ {ml_cfg.MAX_WINDOW})",
        }

    # Reverse so ascending by ts
    readings = readings[::-1]
    df = _readings_to_df(readings)

    # Build features — same code path as training
    feat_df = build_features_for_machine(df, ml_cfg)

    if feat_df.empty:
        return {
            "machine_name":    machine_name,
            "predicted_class": "insufficient_data",
            "probabilities":   {},
            "risk_score":      0.0,
            "model_version":   _meta.get("pipeline_version", "none"),
            "ts":              datetime.now(timezone.utc).isoformat(),
            "note":            "Feature frame empty after engineering",
        }

    if not model_ready:
        return {
            "machine_name":    machine_name,
            "predicted_class": "model_not_trained",
            "probabilities":   {},
            "risk_score":      0.0,
            "model_version":   "none",
            "ts":              datetime.now(timezone.utc).isoformat(),
            "note":            f"No model artifact found at {_MODEL_PATH}. Run ml/train.py first.",
        }

    # Take the last feature row (most recent state)
    import numpy as np
    X = feat_df[_feat_cols].tail(1).astype(float).values

    probas = _model.predict_proba(X)[0]

    # Cost-aware decision rule (same thresholds evaluation picked on the val
    # set); falls back to argmax for artifacts trained before thresholds existed.
    thresholds = _meta.get("decision_thresholds") or {}
    if thresholds:
        pred_idx = int(apply_thresholds(probas.reshape(1, -1), thresholds)[0])
    else:
        pred_idx = int(probas.argmax())
    pred_class = _class_names[pred_idx]

    # risk_score = P(any failure) = 1 - P(none)
    none_idx   = _class_names.index("none") if "none" in _class_names else 0
    risk_score = float(1.0 - probas[none_idx])

    result = {
        "machine_name":    machine_name,
        "predicted_class": pred_class,
        "probabilities":   {_class_names[i]: round(float(p), 4) for i, p in enumerate(probas)},
        "risk_score":      round(risk_score, 4),
        "model_version":   _model_version or _meta.get("pipeline_version", "unknown"),
        "ts":              datetime.now(timezone.utc).isoformat(),
    }

    _log_prediction(machine_name, result, feat_df)
    return result


def predict_all() -> list[dict]:
    """Score all machines currently in machine_readings, sorted by risk (descending)."""
    with get_session() as session:
        from sqlalchemy import distinct
        machines = list(session.scalars(
            select(Reading.machine_name).distinct()
        ).all())

    results = [predict_machine(m) for m in sorted(machines)]
    results.sort(key=lambda r: r.get("risk_score", 0), reverse=True)
    return results


def current_model_summary() -> dict:
    """Return a summary of the loaded model artifact + registry info."""
    _load_model()
    if not _meta:
        return {"status": "no_model", "message": f"Run ml/train.py to train a model."}
    summary = {
        "status":            "loaded",
        "model_version":     _model_version or None,
        "pipeline_version":  _meta.get("pipeline_version"),
        "class_names":       _meta.get("class_names", []),
        "n_features":        len(_feat_cols),
        "H_hours":           _meta.get("H_hours"),
        "window_sizes":      _meta.get("window_sizes"),
        "best_iteration":    _meta.get("best_iteration"),
        "decision_thresholds": _meta.get("decision_thresholds"),
    }
    try:
        from ml.registry import production_row
        row = production_row()
        if row:
            summary["registry"] = {
                "version":     row["version"],
                "stage":       row["stage"],
                "metrics":     row.get("metrics"),
                "trained_at":  row.get("trained_at"),
                "promoted_at": row.get("promoted_at"),
            }
    except Exception:
        pass
    return summary


# ── Prediction logging ────────────────────────────────────────────────────────

def _log_prediction(machine_name: str, result: dict, feat_df: pd.DataFrame) -> None:
    """Write one row to the predictions table (best-effort, non-blocking)."""
    try:
        from app.database import _engine
        from sqlalchemy import text
        import json as _json

        last_row = feat_df.tail(1).iloc[0]
        seq = int(last_row.get("seq", 0)) if "seq" in last_row.index else 0
        sid = str(last_row.get("session_id", "")) if "session_id" in last_row.index else ""
        # ts of the SCORED READING (sim time), not wall clock — the feedback
        # loop joins this against machine_runs.failure_ts.
        row_ts = pd.Timestamp(last_row["ts"]) if "ts" in last_row.index \
            else pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))

        with _engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
                    ts              DATETIME(3) NOT NULL,
                    session_id      VARCHAR(36),
                    seq             INT,
                    machine_name    VARCHAR(64) NOT NULL,
                    predicted_class VARCHAR(32) NOT NULL,
                    probabilities   JSON,
                    model_version   VARCHAR(64),
                    KEY idx_pred_ts      (ts),
                    KEY idx_pred_machine (machine_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.execute(text("""
                INSERT INTO predictions
                    (ts, session_id, seq, machine_name, predicted_class, probabilities, model_version)
                VALUES
                    (:ts, :sid, :seq, :mn, :pc, :pb, :mv)
            """), {
                "ts":  row_ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "sid": sid,
                "seq": seq,
                "mn":  machine_name,
                "pc":  result["predicted_class"],
                "pb":  _json.dumps(result.get("probabilities", {})),
                "mv":  result.get("model_version", ""),
            })
    except Exception:
        pass  # prediction logging is best-effort
