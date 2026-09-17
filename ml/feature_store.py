"""Parquet feature-shard read/write + feature_snapshots catalog helpers.

Shards live at:
  FEATURE_STORE_DIR/<pipeline_version>/<Machine_N>/<start>__<end>.parquet

with columns FEATURE_COLUMNS + [label, session_id, machine_name, ts, seq].
Ranges are half-open [start_ts, end_ts).  The catalog (feature_snapshots) records
each shard's range, row count, class distribution, and a per-feature histogram
reference distribution used by drift detection once raw rows are pruned.

Write protocol (Plan 03 A.2): write parquet → read back and VERIFY → insert
catalog row.  A shard that fails verification is deleted and never catalogued,
so the prune step can trust the catalog completely.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

import ml.config as cfg
from ml.tables import ensure_tables

REF_DIST_BINS = 10


# ── Paths ─────────────────────────────────────────────────────────────────────

def _fmt(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y%m%dT%H%M%S")


def shard_path(pipeline_version: str, machine: str, start_ts, end_ts) -> Path:
    p = (cfg.FEATURE_STORE_DIR / pipeline_version / machine.replace(" ", "_")
         / f"{_fmt(start_ts)}__{_fmt(end_ts)}.parquet")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ── Reference distribution (for drift, A.2.5) ────────────────────────────────

def compute_ref_dist(
    X: np.ndarray,
    feature_columns: list[str],
    bins: int = REF_DIST_BINS,
    max_rows: int = 100_000,
) -> dict:
    """Per-feature histogram {col: {edges: [...], probs: [...]}} for PSI/KS.

    Stored with the sealed shard / model artifact because raw rows are pruned —
    drift detection compares recent features against THIS, not against raw.
    """
    if len(X) > max_rows:
        rng = np.random.default_rng(7)
        X = X[rng.choice(len(X), size=max_rows, replace=False)]

    ref: dict[str, dict] = {}
    for j, col in enumerate(feature_columns):
        v = np.asarray(X[:, j], dtype=np.float64)
        v = v[np.isfinite(v)]
        if len(v) == 0:
            continue
        lo, hi = np.percentile(v, [0.5, 99.5])
        if hi <= lo:
            hi = lo + 1e-6
        counts, edges = np.histogram(v, bins=bins, range=(lo, hi))
        # Two open-ended tail bins so PSI sees mass shifting out of range
        n_below = int((v < lo).sum())
        n_above = int((v > hi).sum())
        probs = np.concatenate([[n_below], counts, [n_above]]).astype(np.float64)
        probs = probs / max(probs.sum(), 1.0)
        ref[col] = {
            "edges": [float(e) for e in edges],
            "probs": [float(p) for p in probs],
            "n":     int(len(v)),
        }
    return ref


# ── Shard write (seal) ────────────────────────────────────────────────────────

def write_shard(
    df: pd.DataFrame,
    machine: str,
    start_ts,
    end_ts,
    engine,
    pipeline_version: str | None = None,
) -> dict:
    """Write one feature shard, verify it, then insert its catalog row.

    Returns the catalog row as a dict.  Raises on verification failure.
    """
    pv   = pipeline_version or cfg.PIPELINE_VERSION
    path = shard_path(pv, machine, start_ts, end_ts)

    df = df.sort_values("ts").reset_index(drop=True)
    df["label"] = df["label"].astype(str)
    df.to_parquet(path, index=False, compression="snappy")

    # ── Verify: read back, row count + class counts must match ──────────────
    check = pd.read_parquet(path, columns=["label"])
    class_counts = df["label"].value_counts().to_dict()
    check_counts = check["label"].value_counts().to_dict()
    if len(check) != len(df) or check_counts != class_counts:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"Shard verification failed for {path}")

    feat_cols = [c for c in cfg_feature_columns() if c in df.columns]
    ref_dist  = compute_ref_dist(df[feat_cols].to_numpy(dtype=np.float32), feat_cols)

    row = {
        "pipeline_version": pv,
        "machine_name":     machine,
        "shard_path":       str(path),
        "range_start_ts":   pd.Timestamp(start_ts),
        "range_end_ts":     pd.Timestamp(end_ts),
        "row_count":        int(len(df)),
        "class_counts":     class_counts,
        "created_at":       datetime.now(timezone.utc).replace(tzinfo=None),
    }

    ensure_tables(engine)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO feature_snapshots
                (pipeline_version, machine_name, shard_path, range_start_ts,
                 range_end_ts, row_count, class_counts, ref_dist, created_at)
            VALUES (:pv, :mn, :sp, :rs, :re, :rc, :cc, :rd, :ca)
        """), {
            "pv": pv, "mn": machine, "sp": str(path),
            "rs": row["range_start_ts"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "re": row["range_end_ts"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "rc": row["row_count"],
            "cc": json.dumps(class_counts),
            "rd": json.dumps(ref_dist),
            "ca": row["created_at"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        })
    return row


def cfg_feature_columns() -> list[str]:
    from ml.features import get_feature_columns
    return get_feature_columns(cfg)


# ── Catalog queries ───────────────────────────────────────────────────────────

def list_shards(engine, pipeline_version: str | None = None,
                machine: str | None = None) -> pd.DataFrame:
    """Catalog rows (sorted by machine, range_start_ts).  Empty frame if none."""
    ensure_tables(engine)
    pv = pipeline_version or cfg.PIPELINE_VERSION
    q = ("SELECT id, pipeline_version, machine_name, shard_path, range_start_ts, "
         "range_end_ts, row_count, class_counts, created_at "
         "FROM feature_snapshots WHERE pipeline_version = :pv")
    params: dict = {"pv": pv}
    if machine:
        q += " AND machine_name = :mn"
        params["mn"] = machine
    q += " ORDER BY machine_name, range_start_ts"
    df = pd.read_sql_query(text(q), engine, params=params)
    for c in ("range_start_ts", "range_end_ts", "created_at"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    return df


def sealed_through(engine, pipeline_version: str | None = None,
                   machine: str | None = None):
    """MAX(range_end_ts) sealed for a machine (or the MIN of the per-machine
    maxima when machine is None — the point up to which ALL machines are sealed).
    Returns pd.Timestamp or None."""
    shards = list_shards(engine, pipeline_version, machine)
    if shards.empty:
        return None
    if machine is not None:
        return shards["range_end_ts"].max()
    per_machine = shards.groupby("machine_name")["range_end_ts"].max()
    return per_machine.min()


def range_already_sealed(engine, machine: str, start_ts, end_ts,
                         pipeline_version: str | None = None) -> bool:
    """True if [start_ts, end_ts) overlaps an existing catalogued shard."""
    ensure_tables(engine)
    pv = pipeline_version or cfg.PIPELINE_VERSION
    with engine.connect() as conn:
        n = conn.execute(text("""
            SELECT COUNT(*) FROM feature_snapshots
            WHERE pipeline_version = :pv AND machine_name = :mn
              AND range_start_ts < :e AND range_end_ts > :s
        """), {
            "pv": pv, "mn": machine,
            "s": pd.Timestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "e": pd.Timestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }).scalar()
    return int(n) > 0


# ── Shard reads (dataset assembly) ────────────────────────────────────────────

def read_shard(path: str | Path, columns: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=columns)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"])
    return df


def latest_ref_dist(engine, pipeline_version: str | None = None) -> dict:
    """Merged ref_dist of the most recent shard per machine (fallback for drift
    when the model bundle carries no reference)."""
    ensure_tables(engine)
    pv = pipeline_version or cfg.PIPELINE_VERSION
    q = text("""
        SELECT fs.ref_dist FROM feature_snapshots fs
        JOIN (SELECT machine_name, MAX(range_end_ts) AS mx
              FROM feature_snapshots WHERE pipeline_version = :pv
              GROUP BY machine_name) t
          ON fs.machine_name = t.machine_name AND fs.range_end_ts = t.mx
        WHERE fs.pipeline_version = :pv
    """)
    with engine.connect() as conn:
        rows = conn.execute(q, {"pv": pv}).fetchall()
    merged: dict = {}
    for (rd,) in rows:
        d = json.loads(rd) if isinstance(rd, (str, bytes)) else (rd or {})
        for col, h in d.items():
            merged.setdefault(col, h)   # first machine wins; good enough as fallback
    return merged
