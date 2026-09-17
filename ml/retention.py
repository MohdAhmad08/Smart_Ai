"""Seal-and-prune job — keeps machine_readings a bounded rolling window
(Plan 03 Part A.2).  Order: seal → verify → prune, idempotent.

Watermarks (anchored to MAX(ts) of the data, not wall clock, so the job works
identically on backfilled sim data and live streams):

  label_complete_ts = anchor − H       only seal rows whose forward label
                                       horizon is complete
  rolling_keep_ts   = anchor − 14 d    never prune raw newer than this
  context margin    = 6 h              raw kept behind the seal point so the
                                       next seal / fresh feature build has
                                       trailing window context

Sealing walks each machine from its sealed_through watermark (from the
feature_snapshots catalog) toward seal_upto in CHUNK_DAYS chunks.  Each chunk
becomes one Parquet shard (features at the training stride + labels) written
via ml.feature_store.write_shard, which verifies the shard before cataloguing
it.  Pruning deletes only raw strictly older than every machine's sealed
watermark minus the context margin — and NEVER touches machine_runs.

Fast path: when a valid full-history feature cache exists
(ml/cache/<pv>/<machine>.parquet with matching db_row_count), the initial bulk
seal slices that cache instead of recomputing — the shards are then exactly
the rows the current model trained on.

CLI
---
  python -m ml.retention                # seal + prune
  python -m ml.retention --dry-run      # report what would happen
  python -m ml.retention --no-prune     # seal + verify only
"""
from __future__ import annotations

import argparse
import time
from datetime import timedelta

import pandas as pd
from sqlalchemy import text

import ml.config as cfg
from ml.db import (
    get_engine, iter_machines, load_runs, load_readings_range,
    machine_ts_range, ts_range,
)
from ml.features import build_features_for_machine, get_feature_columns
from ml.labels import build_labels
from ml.feature_store import (
    write_shard, sealed_through, range_already_sealed, list_shards,
)
from ml.tables import ensure_tables

ROLLING_KEEP_DAYS  = 14
CHUNK_DAYS         = 30
CONTEXT_HOURS      = 6          # raw context kept behind the seal point
PRUNE_BATCH_ROWS   = 50_000     # bounded per-statement delete (undo-log safety)

_META_COLS = ["session_id", "machine_name", "ts", "seq", "label"]


# ── Seal helpers ──────────────────────────────────────────────────────────────

def _cached_full_frame(machine: str, engine) -> pd.DataFrame | None:
    """Return the training feature cache for a machine if it is still valid
    (row-count attr matches the DB) — the initial-seal fast path."""
    p = cfg.ML_ROOT / "cache" / cfg.PIPELINE_VERSION / f"{machine.replace(' ', '_')}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        with engine.connect() as conn:
            n = conn.execute(
                text("SELECT COUNT(*) FROM machine_readings WHERE machine_name = :m"),
                {"m": machine},
            ).scalar()
        if df.attrs.get("db_row_count") != int(n):
            return None
        df["ts"] = pd.to_datetime(df["ts"])
        df["label"] = df["label"].astype(str)
        return df
    except Exception:
        return None


def _build_chunk_features(engine, machine: str, start_ts, end_ts,
                          runs_df: pd.DataFrame) -> pd.DataFrame:
    """Build labelled feature rows for [start_ts, end_ts) from raw readings,
    loading CONTEXT_HOURS of trailing raw so the first rows have full windows."""
    ctx_start = pd.Timestamp(start_ts) - timedelta(hours=CONTEXT_HOURS)
    raw = load_readings_range(engine, machine, ctx_start, end_ts, include_truth=False)
    if raw.empty:
        return pd.DataFrame()

    part = build_features_for_machine(raw, cfg)
    del raw
    if part.empty:
        return pd.DataFrame()

    part = part[(part["ts"] >= pd.Timestamp(start_ts))
                & (part["ts"] < pd.Timestamp(end_ts))].reset_index(drop=True)
    if part.empty:
        return pd.DataFrame()

    part["label"] = build_labels(part, runs_df, cfg.H_SECONDS).values
    part["label"] = part["label"].fillna("none").astype(str)
    return part


def seal_machine(engine, machine: str, seal_upto: pd.Timestamp,
                 runs_df: pd.DataFrame, dry_run: bool = False,
                 chunk_days: int = CHUNK_DAYS) -> int:
    """Advance one machine's sealed watermark to seal_upto.  Returns rows sealed."""
    feat_cols = get_feature_columns(cfg)
    start = sealed_through(engine, machine=machine)
    if start is None:
        mn, _ = machine_ts_range(engine, machine)
        if mn is None:
            return 0
        start = mn

    if start >= seal_upto:
        print(f"  {machine}: already sealed through {start} — nothing to do")
        return 0

    cached = None if dry_run else _cached_full_frame(machine, engine)
    if cached is not None:
        print(f"  {machine}: using valid feature cache ({len(cached):,} rows) as seal source")

    total = 0
    cursor = start
    while cursor < seal_upto:
        chunk_end = min(cursor + timedelta(days=chunk_days), seal_upto)

        if range_already_sealed(engine, machine, cursor, chunk_end):
            print(f"  {machine}: [{cursor} .. {chunk_end}) already sealed — skip")
            cursor = chunk_end
            continue

        if dry_run:
            print(f"  {machine}: would seal [{cursor} .. {chunk_end})")
            cursor = chunk_end
            continue

        if cached is not None:
            part = cached[(cached["ts"] >= cursor) & (cached["ts"] < chunk_end)]
            part = part[feat_cols + _META_COLS].reset_index(drop=True)
        else:
            part = _build_chunk_features(engine, machine, cursor, chunk_end, runs_df)
            if not part.empty:
                part = part[feat_cols + _META_COLS]

        if part.empty:
            print(f"  {machine}: [{cursor} .. {chunk_end}) no rows — skip")
        else:
            write_shard(part, machine, cursor, chunk_end, engine)
            total += len(part)
            print(f"  {machine}: sealed [{cursor} .. {chunk_end})  {len(part):,} rows")
        del part
        cursor = chunk_end

    return total


# ── Prune ─────────────────────────────────────────────────────────────────────

def prune_old_readings(engine=None, dry_run: bool = False) -> int:
    """Batched delete of raw readings that are (a) older than the rolling
    window AND (b) sealed for EVERY machine, minus the context margin.
    NEVER touches machine_runs."""
    engine = engine or get_engine()
    ensure_tables(engine)

    _, anchor = ts_range(engine)
    rolling_keep_ts = anchor - timedelta(days=ROLLING_KEEP_DAYS)

    global_sealed = sealed_through(engine)   # min over machines
    if global_sealed is None:
        print("prune: nothing sealed yet — refusing to prune")
        return 0

    cutoff = min(rolling_keep_ts, global_sealed) - timedelta(hours=CONTEXT_HOURS)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM machine_readings WHERE ts < :c"),
            {"c": cutoff_str},
        ).scalar()
    n = int(n)

    if dry_run:
        print(f"[dry-run] Would prune {n:,} readings older than {cutoff_str} "
              f"(rolling_keep={rolling_keep_ts}, sealed_through={global_sealed})")
        return n

    if n == 0:
        print(f"prune: no rows older than {cutoff_str}")
        return 0

    print(f"prune: deleting {n:,} readings older than {cutoff_str} "
          f"in batches of {PRUNE_BATCH_ROWS:,} ...")
    deleted = 0
    t0 = time.time()
    while True:
        with engine.begin() as conn:
            res = conn.execute(
                text("DELETE FROM machine_readings WHERE ts < :c LIMIT :lim"),
                {"c": cutoff_str, "lim": PRUNE_BATCH_ROWS},
            )
        if res.rowcount == 0:
            break
        deleted += res.rowcount
        print(f"  ... {deleted:,}/{n:,}", flush=True)
    print(f"prune: deleted {deleted:,} rows in {time.time()-t0:.0f}s "
          f"(machine_runs untouched)")
    return deleted


# ── Orchestrator ──────────────────────────────────────────────────────────────

def seal_and_prune(prune: bool = True, dry_run: bool = False,
                   chunk_days: int = CHUNK_DAYS) -> dict:
    """The nightly job (Plan 03 C.2): seal → verify → prune.  Returns a summary."""
    engine = get_engine()
    ensure_tables(engine)

    ts_min, anchor = ts_range(engine)
    rolling_keep_ts   = anchor - timedelta(days=ROLLING_KEEP_DAYS)
    label_complete_ts = anchor - timedelta(hours=cfg.H_HOURS)
    seal_upto = min(rolling_keep_ts, label_complete_ts)

    print(f"seal_and_prune  pipeline={cfg.PIPELINE_VERSION}")
    print(f"  data range        : {ts_min} .. {anchor}")
    print(f"  rolling_keep_ts   : {rolling_keep_ts}")
    print(f"  label_complete_ts : {label_complete_ts}")
    print(f"  seal_upto         : {seal_upto}")

    runs_df = load_runs(engine)
    sealed_rows = 0
    for machine in iter_machines(engine):
        sealed_rows += seal_machine(engine, machine, seal_upto, runs_df,
                                    dry_run=dry_run, chunk_days=chunk_days)

    pruned = prune_old_readings(engine, dry_run=dry_run) if prune else 0

    shards = list_shards(engine)
    summary = {
        "sealed_rows":    sealed_rows,
        "pruned_rows":    pruned,
        "total_shards":   int(len(shards)),
        "sealed_through": str(sealed_through(engine)),
    }
    print(f"done: {summary}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seal aged raw into Parquet shards, then prune.")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--no-prune", action="store_true")
    parser.add_argument("--chunk-days", type=int, default=CHUNK_DAYS)
    args = parser.parse_args()
    seal_and_prune(prune=not args.no_prune, dry_run=args.dry_run,
                   chunk_days=args.chunk_days)
