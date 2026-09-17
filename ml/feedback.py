"""Monitoring / feedback loop (Plan 03 Part E) — the "self-improving" story.

Joins live predictions back to the failures that actually happened:

  recall     per class: of the failures in the window, how many had at least
             one correct-class prediction inside the H hours before failure_ts?
  lead time  per detected failure: failure_ts − earliest correct prediction.
  precision  per class: of the class-c predictions whose forward horizon is
             complete (ts ≤ anchor − H), how many were followed by a real
             c-failure of that machine within H?  (Newer predictions are
             censored — the failure may still be coming — and are excluded.)

Timestamps are SIM time: predictions.ts records the scored reading's ts
(prediction_service) and machine_runs.failure_ts is generator time, so the
join is consistent for both backfilled and live data.

Results are written to live_metrics and surfaced on the dashboard via
/api/model/health.

CLI:  python -m ml.feedback  [--days 7]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text

import ml.config as cfg
from ml.db import get_engine, load_runs
from ml.tables import ensure_tables


def _load_predictions(engine, start_ts, end_ts) -> pd.DataFrame:
    q = text(
        "SELECT ts, machine_name, predicted_class, model_version "
        "FROM predictions WHERE ts >= :s AND ts <= :e"
    )
    df = pd.read_sql_query(q, engine, params={
        "s": pd.Timestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "e": pd.Timestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    })
    if len(df):
        df["ts"] = pd.to_datetime(df["ts"])
    return df


def evaluate_live_outcomes(window_days: int = 7, write: bool = True) -> dict:
    """Match predictions → subsequent machine_runs failures within H.
    Returns per-class live precision / recall / lead-time and stores them."""
    engine = get_engine()
    ensure_tables(engine)
    H = timedelta(hours=cfg.H_HOURS)

    with engine.connect() as conn:
        anchor = conn.execute(text("SELECT MAX(ts) FROM predictions")).scalar()
    if anchor is None:
        print("feedback: predictions table is empty — nothing to evaluate")
        return {"window_days": window_days, "classes": {}, "n_predictions": 0}

    anchor = pd.Timestamp(anchor)
    win_start = anchor - timedelta(days=window_days)

    preds = _load_predictions(engine, win_start, anchor)
    runs  = load_runs(engine)
    fails = runs[(runs["failure_ts"] >= win_start - H)
                 & (runs["failure_ts"] <= anchor + H)]

    model_version = ""
    if len(preds) and preds["model_version"].notna().any():
        model_version = str(preds["model_version"].dropna().iloc[-1])

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    per_class: dict[str, dict] = {}

    for cls in cfg.CLASS_NAMES:
        if cls == "none":
            continue
        p_c = preds[preds["predicted_class"] == cls]
        f_c = fails[(fails["component"] == cls)
                    & (fails["failure_ts"] >= win_start)
                    & (fails["failure_ts"] <= anchor)]

        # Recall + lead time over actual failures
        detected, lead_hours = 0, []
        for _, f in f_c.iterrows():
            m_preds = p_c[(p_c["machine_name"] == f["machine_name"])
                          & (p_c["ts"] >= f["failure_ts"] - H)
                          & (p_c["ts"] <= f["failure_ts"])]
            if len(m_preds):
                detected += 1
                first = m_preds["ts"].min()
                lead_hours.append((f["failure_ts"] - first).total_seconds() / 3600.0)

        recall = detected / len(f_c) if len(f_c) else None

        # Precision over horizon-complete predictions
        mature = p_c[p_c["ts"] <= anchor - H]
        tp = 0
        for _, p in mature.iterrows():
            hit = fails[(fails["component"] == cls)
                        & (fails["machine_name"] == p["machine_name"])
                        & (fails["failure_ts"] >= p["ts"])
                        & (fails["failure_ts"] <= p["ts"] + H)]
            if len(hit):
                tp += 1
        precision = tp / len(mature) if len(mature) else None

        per_class[cls] = {
            "precision":          None if precision is None else round(precision, 4),
            "recall":             None if recall is None else round(recall, 4),
            "lead_time_median_h": (round(float(np.median(lead_hours)), 2)
                                   if lead_hours else None),
            "n_predictions":      int(len(p_c)),
            "n_mature_predictions": int(len(mature)),
            "n_failures":         int(len(f_c)),
            "n_detected":         detected,
        }

    if write:
        with engine.begin() as conn:
            for cls, d in per_class.items():
                conn.execute(text("""
                    INSERT INTO live_metrics
                        (ts, window_days, class_name, precision_score, recall_score,
                         lead_time_median_h, n_predictions, n_failures, model_version)
                    VALUES (:ts, :wd, :cn, :p, :r, :lt, :np, :nf, :mv)
                """), {
                    "ts": now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    "wd": window_days, "cn": cls,
                    "p": d["precision"], "r": d["recall"],
                    "lt": d["lead_time_median_h"],
                    "np": d["n_predictions"], "nf": d["n_failures"],
                    "mv": model_version,
                })

    summary = {
        "window_days":   window_days,
        "anchor":        str(anchor),
        "n_predictions": int(len(preds)),
        "n_failures":    int(len(fails)),
        "model_version": model_version,
        "classes":       per_class,
        "ts":            str(now),
    }

    print(f"feedback: window={window_days}d anchor={anchor}  "
          f"{len(preds):,} predictions, {len(fails)} failures")
    for cls, d in per_class.items():
        print(f"  {cls:12s} recall={d['recall']} precision={d['precision']} "
              f"lead_median={d['lead_time_median_h']}h "
              f"(preds={d['n_predictions']}, failures={d['n_failures']})")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    evaluate_live_outcomes(window_days=args.days, write=not args.no_write)
