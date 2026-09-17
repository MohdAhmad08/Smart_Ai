"""Model-health panel data (Plan 03 Parts D/E/F) — registry pointer, live
feedback metrics, and drift status for the dashboard."""
from __future__ import annotations

import json
from sqlalchemy import text

from app.database import _engine


def _rows(q: str, **params) -> list[dict]:
    with _engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(q), params).mappings().all()]


def _parse_json(v):
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


def get_registry(limit: int = 20) -> list[dict]:
    """Model version history (newest first)."""
    try:
        rows = _rows(
            "SELECT version, stage, pipeline_version, metrics, mlflow_run_id, "
            "trained_at, promoted_at FROM model_registry ORDER BY id DESC LIMIT :n",
            n=limit)
    except Exception:
        return []
    for r in rows:
        r["metrics"] = _parse_json(r.get("metrics"))
        for k in ("trained_at", "promoted_at"):
            if r.get(k) is not None:
                r[k] = str(r[k])
    return rows


def _latest_live_metrics() -> dict:
    """Most recent feedback-loop row per class."""
    try:
        rows = _rows("""
            SELECT lm.class_name, lm.precision_score, lm.recall_score,
                   lm.lead_time_median_h, lm.n_predictions, lm.n_failures,
                   lm.window_days, lm.ts, lm.model_version
            FROM live_metrics lm
            JOIN (SELECT class_name, MAX(id) AS mx FROM live_metrics
                  GROUP BY class_name) t
              ON lm.class_name = t.class_name AND lm.id = t.mx
        """)
    except Exception:
        return {}
    out = {}
    for r in rows:
        cls = r.pop("class_name")
        if r.get("ts") is not None:
            r["ts"] = str(r["ts"])
        out[cls] = r
    return out


def _latest_drift() -> dict:
    """Summary of the most recent drift check."""
    try:
        last = _rows("SELECT MAX(ts) AS ts FROM drift_metrics")
        if not last or last[0]["ts"] is None:
            return {}
        ts = last[0]["ts"]
        rows = _rows(
            "SELECT feature, psi, ks_p, flag FROM drift_metrics WHERE ts = :t "
            "ORDER BY psi DESC", t=ts)
    except Exception:
        return {}
    n_sig = sum(1 for r in rows if r["flag"] == "significant")
    n_mod = sum(1 for r in rows if r["flag"] == "moderate")
    return {
        "checked_at":    str(ts),
        "n_features":    len(rows),
        "n_significant": n_sig,
        "n_moderate":    n_mod,
        "status": ("significant" if n_sig >= 5 else
                   "moderate" if (n_sig + n_mod) > 0 else "stable"),
        "top": [{**r, "psi": round(float(r["psi"]), 4) if r["psi"] is not None else None}
                for r in rows[:8]],
    }


def get_model_health() -> dict:
    """Everything the dashboard model-health panel needs in one call."""
    registry = get_registry(limit=5)
    production = next((r for r in registry if r["stage"] == "Production"), None)

    try:
        pred_count = _rows(
            "SELECT COUNT(*) AS n, MAX(ts) AS last_ts FROM predictions")[0]
        predictions = {"total": int(pred_count["n"]),
                       "last_ts": str(pred_count["last_ts"]) if pred_count["last_ts"] else None}
    except Exception:
        predictions = {"total": 0, "last_ts": None}

    return {
        "production":   production,
        "recent_versions": registry,
        "live_metrics": _latest_live_metrics(),
        "drift":        _latest_drift(),
        "predictions":  predictions,
    }
