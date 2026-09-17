"""Drift detection (Plan 03 Part D).

Compares RECENT rolling-window feature distributions against the STORED
training reference (metadata["ref_dist"] of the Production model, falling back
to the sealed-shard catalog's ref_dist) — raw history is pruned, so the
reference must travel with the model/snapshot (A.2.5).

Metrics per feature:
  PSI  = Σ (recent% − ref%) · ln(recent% / ref%)   over the stored bins
         <0.1 stable | 0.1–0.25 moderate | >0.25 significant
  KS   = max |CDF_ref − CDF_recent| over the same bins, with an asymptotic
         p-value (approximate — computed from binned CDFs, not raw samples)

Plus prediction drift: the predicted-class rate over recent rows in the
`predictions` table vs the training class base rates.

Results land in drift_metrics {ts, feature, psi, ks_p, flag, model_version};
`check_drift()` returns a summary with `retrain_recommended` used by
ml/schedule.py to trigger a retrain.

CLI:  python -m ml.drift  [--days 3]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text

import ml.config as cfg
from ml.db import get_engine, iter_machines, load_readings_range, ts_range
from ml.features import build_features_for_machine, get_feature_columns
from ml.feature_store import latest_ref_dist
from ml.tables import ensure_tables

DRIFT_RECENT_DAYS   = 3
PSI_MODERATE        = 0.10
PSI_SIGNIFICANT     = 0.25
MIN_SIGNIFICANT     = 5      # features flagged significant before a retrain is recommended
_EPS                = 1e-6

# Monotone-by-design features (cumulative counters) ALWAYS drift against a
# long training reference — scoring them would trigger a retrain every check.
DRIFT_EXCLUDE_FEATURES = {"machine_time_h"}


# ── Reference ─────────────────────────────────────────────────────────────────

def _production_reference(engine) -> tuple[dict, dict, str]:
    """(ref_dist, class_base_rates, model_version) — from the Production model
    bundle when available, else the sealed-shard catalog."""
    ref, base_rates, version = {}, {}, ""
    try:
        from ml.registry import production_row
        row = production_row(engine)
        if row is not None:
            version = row["version"]
            from pathlib import Path
            meta_p = Path(row["artifact_path"]) / "metadata.json"
            if meta_p.exists():
                meta = json.loads(meta_p.read_text())
                ref = meta.get("ref_dist") or {}
                base_rates = meta.get("class_base_rates") or {}
    except Exception:
        pass

    if not ref:
        ref = latest_ref_dist(engine)

    if not base_rates:
        # Fall back to sealed-shard label distribution
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT class_counts FROM feature_snapshots WHERE pipeline_version = :pv"
            ), {"pv": cfg.PIPELINE_VERSION}).fetchall()
        totals: dict[str, float] = {}
        for (cc,) in rows:
            d = json.loads(cc) if isinstance(cc, (str, bytes)) else (cc or {})
            for k, v in d.items():
                totals[k] = totals.get(k, 0.0) + float(v)
        s = sum(totals.values())
        if s > 0:
            base_rates = {k: v / s for k, v in totals.items()}

    return ref, base_rates, version


# ── Recent features ───────────────────────────────────────────────────────────

def _recent_features(engine, days: int) -> pd.DataFrame:
    _, anchor = ts_range(engine)
    start = anchor - timedelta(days=days)
    parts = []
    for machine in iter_machines(engine):
        raw = load_readings_range(engine, machine, start,
                                  anchor + timedelta(seconds=1), include_truth=False)
        if raw.empty:
            continue
        f = build_features_for_machine(raw, cfg)
        del raw
        if not f.empty:
            parts.append(f)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


# ── PSI / KS on stored histograms ─────────────────────────────────────────────

def _bin_recent(values: np.ndarray, edges: list[float]) -> np.ndarray:
    """Histogram of recent values over stored edges + two open tail bins,
    normalised to probabilities (matches compute_ref_dist layout)."""
    e = np.asarray(edges, dtype=np.float64)
    v = values[np.isfinite(values)]
    if len(v) == 0:
        return np.array([])
    counts, _ = np.histogram(v, bins=e)
    below = int((v < e[0]).sum())
    above = int((v > e[-1]).sum())
    probs = np.concatenate([[below], counts, [above]]).astype(np.float64)
    return probs / max(probs.sum(), 1.0)


def _psi(ref_probs: np.ndarray, rec_probs: np.ndarray) -> float:
    p = np.clip(np.asarray(ref_probs, dtype=np.float64), _EPS, None)
    q = np.clip(np.asarray(rec_probs, dtype=np.float64), _EPS, None)
    p, q = p / p.sum(), q / q.sum()
    return float(np.sum((q - p) * np.log(q / p)))


def _ks(ref_probs: np.ndarray, rec_probs: np.ndarray,
        n_ref: int, n_rec: int) -> tuple[float, float]:
    p = np.asarray(ref_probs, dtype=np.float64); p = p / max(p.sum(), _EPS)
    q = np.asarray(rec_probs, dtype=np.float64); q = q / max(q.sum(), _EPS)
    d = float(np.max(np.abs(np.cumsum(p) - np.cumsum(q))))
    try:
        from scipy.stats import kstwobign
        n_eff = max((n_ref * n_rec) / max(n_ref + n_rec, 1), 1.0)
        p_val = float(kstwobign.sf(d * np.sqrt(n_eff)))
    except Exception:
        p_val = float("nan")
    return d, p_val


def _flag(psi: float) -> str:
    if psi >= PSI_SIGNIFICANT:
        return "significant"
    if psi >= PSI_MODERATE:
        return "moderate"
    return "stable"


# ── Prediction drift ──────────────────────────────────────────────────────────

def _prediction_drift(engine, base_rates: dict, days: int) -> dict | None:
    ensure_tables(engine)
    with engine.connect() as conn:
        anchor = conn.execute(text("SELECT MAX(ts) FROM predictions")).scalar()
        if anchor is None:
            return None
        start = pd.Timestamp(anchor) - timedelta(days=days)
        rows = conn.execute(text(
            "SELECT predicted_class, COUNT(*) FROM predictions "
            "WHERE ts >= :s GROUP BY predicted_class"
        ), {"s": start.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}).fetchall()

    counts = {r[0]: float(r[1]) for r in rows
              if r[0] in cfg.CLASS_NAMES}
    n = sum(counts.values())
    if n < 20 or not base_rates:
        return None   # not enough live predictions to judge

    rec = np.array([counts.get(c, 0.0) / n for c in cfg.CLASS_NAMES])
    ref = np.array([float(base_rates.get(c, 0.0)) for c in cfg.CLASS_NAMES])
    psi = _psi(ref, rec)
    return {"psi": psi, "n": int(n), "flag": _flag(psi),
            "recent_rates": {c: round(float(r), 4) for c, r in zip(cfg.CLASS_NAMES, rec)}}


# ── Main check ────────────────────────────────────────────────────────────────

def check_drift(days: int = DRIFT_RECENT_DAYS, write: bool = True) -> dict:
    engine = get_engine()
    ensure_tables(engine)

    ref, base_rates, model_version = _production_reference(engine)
    if not ref:
        print("drift: no reference distribution available (train/seal first)")
        return {"checked": 0, "retrain_recommended": False}

    recent = _recent_features(engine, days)
    if recent.empty:
        print("drift: no recent readings to check")
        return {"checked": 0, "retrain_recommended": False}

    feat_cols = [c for c in get_feature_columns(cfg)
                 if c in ref and c not in DRIFT_EXCLUDE_FEATURES]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    results: list[dict] = []

    for col in feat_cols:
        h = ref[col]
        rec_probs = _bin_recent(recent[col].to_numpy(dtype=np.float64), h["edges"])
        if rec_probs.size == 0:
            continue
        psi = _psi(h["probs"], rec_probs)
        ks_d, ks_p = _ks(h["probs"], rec_probs, int(h.get("n", 1000)), len(recent))
        results.append({"feature": col, "psi": psi, "ks_p": ks_p, "flag": _flag(psi)})

    pred_drift = _prediction_drift(engine, base_rates, days)
    if pred_drift is not None:
        results.append({"feature": "__predicted_class_rates__",
                        "psi": pred_drift["psi"], "ks_p": None,
                        "flag": pred_drift["flag"]})

    if write and results:
        with engine.begin() as conn:
            for r in results:
                conn.execute(text("""
                    INSERT INTO drift_metrics (ts, feature, psi, ks_p, flag, model_version)
                    VALUES (:ts, :f, :psi, :ksp, :fl, :mv)
                """), {
                    "ts": now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    "f": r["feature"], "psi": r["psi"], "ksp": r["ks_p"],
                    "fl": r["flag"], "mv": model_version,
                })

    significant = [r for r in results if r["flag"] == "significant"]
    moderate    = [r for r in results if r["flag"] == "moderate"]
    pred_flag   = pred_drift is not None and pred_drift["flag"] == "significant"
    recommended = len(significant) >= MIN_SIGNIFICANT or pred_flag

    summary = {
        "checked":             len(results),
        "recent_rows":         int(len(recent)),
        "recent_days":         days,
        "model_version":       model_version,
        "n_significant":       len(significant),
        "n_moderate":          len(moderate),
        "max_psi":             max((r["psi"] for r in results), default=0.0),
        "top_drifted":         sorted(results, key=lambda r: -r["psi"])[:10],
        "prediction_drift":    pred_drift,
        "retrain_recommended": recommended,
        "ts":                  str(now),
    }

    print(f"drift: checked {summary['checked']} features over last {days}d "
          f"({summary['recent_rows']:,} rows)  "
          f"significant={summary['n_significant']} moderate={summary['n_moderate']} "
          f"max_psi={summary['max_psi']:.3f}  retrain={recommended}")
    for r in summary["top_drifted"][:5]:
        print(f"  {r['feature']:32s} PSI={r['psi']:.3f}  [{r['flag']}]")
    if pred_drift:
        print(f"  predicted-class rates PSI={pred_drift['psi']:.3f} "
              f"[{pred_drift['flag']}]  n={pred_drift['n']}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DRIFT_RECENT_DAYS)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    check_drift(days=args.days, write=not args.no_write)
