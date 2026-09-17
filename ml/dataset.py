"""Dataset assembly and leakage-safe train/val/test splitting.

Sources (Plan 02 B.5 / Plan 03 C.1)
-----------------------------------
Union of two sources, per machine:
  (a) sealed Parquet shards of the current pipeline_version (the aged, frozen
      history — read via ml/feature_store.py catalog), and
  (b) features freshly extracted from the rolling raw window
      (machine_readings rows after the machine's sealed_through watermark).

When no shards exist yet (pre-lifecycle installs) the legacy path builds the
whole history from raw via the per-machine cache at
ml/cache/<pipeline_version>/<Machine_N>.parquet.

Splitting strategy
------------------
- Train : first TRAIN_FRAC of the assembled timeline.
- Val   : next slice up to VAL_FRAC, with a GAP_HOURS gap (horizon bleed).
- Test  : stratified sample of failure rows (+ matching none rows) drawn from
          the post-val remainder, so all classes appear in test.

Memory strategy
---------------
Pass 1 collects only (ts, label) per machine (a few MB), computes split masks
and exact split sizes.  Pass 2 pre-allocates the final arrays and fills them
shard-by-shard — peak RAM is one 30-day shard (~50k rows) plus the output
arrays, never a full machine frame.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text
from sklearn.preprocessing import LabelEncoder

import ml.config as cfg
from ml.db import (
    get_engine, load_readings, load_readings_range, load_runs,
    iter_machines, machine_ts_range,
)
from ml.features import build_features_for_machine, get_feature_columns
from ml.labels import build_labels, build_labels_from_truth_json
from ml.feature_store import list_shards, read_shard

_CACHE_DIR = cfg.ML_ROOT / "cache" / cfg.PIPELINE_VERSION
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Fraction of failure rows to reserve for test (stratified, not time-based)
_TEST_FAILURE_FRAC = 0.15
_RNG_SEED = 42
_FRESH_CONTEXT_HOURS = 6   # raw context loaded before the sealed boundary


# ── Legacy cache helpers (used only when no shards exist yet) ─────────────────

def _cache_path(machine: str) -> Path:
    return _CACHE_DIR / f"{machine.replace(' ', '_')}.parquet"


def _db_row_count(engine, machine: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(
            text("SELECT COUNT(*) FROM machine_readings WHERE machine_name = :m"),
            {"m": machine},
        ).scalar())


def _load_cached(machine: str, expected_rows: int) -> pd.DataFrame | None:
    p = _cache_path(machine)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if df.attrs.get("db_row_count") == expected_rows:
            return df
    except Exception:
        pass
    return None


def _save_cache(machine: str, feat_df: pd.DataFrame, db_rows: int) -> None:
    p = _cache_path(machine)
    df = feat_df.copy()
    df["label"] = df["label"].astype("category")
    df.attrs["db_row_count"] = db_rows
    df.to_parquet(p, index=False)


def _build_and_cache(engine, machine: str, runs_df: pd.DataFrame,
                     use_truth_json: bool, db_rows: int) -> pd.DataFrame:
    """Legacy full-history build from raw (only used when no shards exist)."""
    mdf  = load_readings(engine, machine_name=machine, include_truth=True)
    part = build_features_for_machine(mdf, cfg)

    if part.empty:
        del mdf
        return pd.DataFrame()

    if use_truth_json:
        truth_map = (
            mdf[["ts", "truth_json"]]
            .drop_duplicates("ts")
            .set_index("ts")["truth_json"]
        )
        pfl = part[["machine_name", "ts"]].copy()
        pfl["truth_json"] = pfl["ts"].map(truth_map)
        labels = build_labels_from_truth_json(pfl, cfg.H_SECONDS)
    else:
        labels = build_labels(part, runs_df, cfg.H_SECONDS)

    part["label"] = labels.values
    part["label"] = part["label"].fillna("none")
    del mdf

    _save_cache(machine, part, db_rows)
    return part


# ── Fresh (rolling-window) feature build ──────────────────────────────────────

def _build_fresh(engine, machine: str, boundary_ts, runs_df: pd.DataFrame,
                 use_truth_json: bool) -> pd.DataFrame:
    """Features + labels for raw rows with ts >= boundary_ts (the un-sealed
    tail).  Loads _FRESH_CONTEXT_HOURS of raw before the boundary so rolling
    windows are warm at the boundary."""
    mn, mx = machine_ts_range(engine, machine)
    if mn is None:
        return pd.DataFrame()

    boundary = pd.Timestamp(boundary_ts) if boundary_ts is not None else mn
    ctx_start = max(mn, boundary - timedelta(hours=_FRESH_CONTEXT_HOURS))

    raw = load_readings_range(engine, machine, ctx_start, mx + timedelta(seconds=1),
                              include_truth=use_truth_json)
    if raw.empty:
        return pd.DataFrame()

    part = build_features_for_machine(raw, cfg)
    if part.empty:
        del raw
        return pd.DataFrame()

    if use_truth_json:
        truth_map = (
            raw[["ts", "truth_json"]]
            .drop_duplicates("ts")
            .set_index("ts")["truth_json"]
        )
        pfl = part[["machine_name", "ts"]].copy()
        pfl["truth_json"] = pfl["ts"].map(truth_map)
        labels = build_labels_from_truth_json(pfl, cfg.H_SECONDS)
    else:
        labels = build_labels(part, runs_df, cfg.H_SECONDS)
    part["label"] = labels.values
    part["label"] = part["label"].fillna("none").astype(str)
    del raw

    part = part[part["ts"] >= boundary].reset_index(drop=True)
    return part


# ── Label encoding ────────────────────────────────────────────────────────────

def _make_le() -> LabelEncoder:
    le = LabelEncoder()
    le.classes_ = np.array(cfg.CLASS_NAMES)
    return le


def _encode(y_series: pd.Series, le: LabelEncoder) -> np.ndarray:
    y_plain = np.asarray(pd.Series(y_series).fillna("none"), dtype=object).astype(str)
    return le.transform(y_plain).astype(np.int32)


# ── Stratified test mask ──────────────────────────────────────────────────────

def _stratified_test_mask(y_np: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Boolean mask picking TEST rows: TEST_FAILURE_FRAC of each failure class
    plus an equal count of 'none' rows."""
    mask = np.zeros(len(y_np), dtype=bool)
    failure_test_count = 0

    for cls in range(1, cfg.N_CLASSES):   # skip class 0 = "none"
        idx = np.where(y_np == cls)[0]
        if len(idx) == 0:
            continue
        n_pick = max(1, int(len(idx) * _TEST_FAILURE_FRAC))
        chosen = rng.choice(idx, size=n_pick, replace=False)
        mask[chosen] = True
        failure_test_count += n_pick

    none_idx = np.where(y_np == 0)[0]
    n_none = min(failure_test_count, len(none_idx))
    if n_none > 0:
        chosen_none = rng.choice(none_idx, size=n_none, replace=False)
        mask[chosen_none] = True

    return mask


# ── Per-machine part iteration ────────────────────────────────────────────────

class _MachineParts:
    """Ordered list of frame sources for one machine: sealed shards (by
    range_start) followed by the fresh tail.  Iterating yields DataFrames one
    at a time so pass 2 never holds a whole machine in RAM."""

    def __init__(self, machine: str, shard_paths: list[str],
                 fresh_frame: pd.DataFrame | None,
                 legacy_frame_loader=None):
        self.machine       = machine
        self.shard_paths   = shard_paths
        self.fresh_frame   = fresh_frame
        self.legacy_loader = legacy_frame_loader   # () -> DataFrame

    def iter_frames(self):
        if self.legacy_loader is not None:
            df = self.legacy_loader()
            if df is not None and not df.empty:
                yield df
            return
        for p in self.shard_paths:
            yield read_shard(p)
        if self.fresh_frame is not None and not self.fresh_frame.empty:
            yield self.fresh_frame

    def meta(self) -> tuple[np.ndarray, pd.Series]:
        """(ts ndarray[datetime64], label Series) across all parts, in order."""
        ts_parts, lb_parts = [], []
        if self.legacy_loader is not None:
            df = self.legacy_loader()
            if df is not None and not df.empty:
                ts_parts.append(pd.to_datetime(df["ts"]).to_numpy())
                lb_parts.append(df["label"].astype(str))
        else:
            for p in self.shard_paths:
                df = read_shard(p, columns=["ts", "label"])
                ts_parts.append(df["ts"].to_numpy())
                lb_parts.append(df["label"].astype(str))
            if self.fresh_frame is not None and not self.fresh_frame.empty:
                ts_parts.append(pd.to_datetime(self.fresh_frame["ts"]).to_numpy())
                lb_parts.append(self.fresh_frame["label"].astype(str))
        if not ts_parts:
            return np.array([], dtype="datetime64[ns]"), pd.Series(dtype=object)
        return (np.concatenate(ts_parts),
                pd.concat(lb_parts, ignore_index=True))


# ── Main entry point ──────────────────────────────────────────────────────────

def make_datasets(verbose: bool = True) -> dict:
    """Assemble train/val/test from (sealed shards ∪ rolling raw).

    Returns dict with X_train/val/test, y_*, groups_*, feature_columns,
    label_encoder, meta_test, manifest.
    """
    engine    = get_engine()
    feat_cols = get_feature_columns(cfg)
    n_feats   = len(feat_cols)
    le        = _make_le()

    if verbose:
        print("Loading machine_runs from MySQL ...")
    runs_df = load_runs(engine)
    use_truth_json = len(runs_df) == 0
    if verbose:
        print(f"  {len(runs_df):,} failure events")
        if use_truth_json:
            print("  machine_runs empty -- labels from truth_json")

    machines  = iter_machines(engine)
    shard_cat = list_shards(engine)                 # current pipeline_version
    use_shards = not shard_cat.empty

    if verbose:
        print(f"  {len(machines)} machines: {machines}")
        print(f"  Source: {'sealed shards + rolling raw' if use_shards else 'raw (legacy cache)'}"
              + (f"  [{len(shard_cat)} shards]" if use_shards else ""))

    # ── Build per-machine part lists ─────────────────────────────────────────
    manifest: dict = {
        "pipeline_version": cfg.PIPELINE_VERSION,
        "shards": [],
        "fresh":  {},
        "machines": machines,
    }
    parts_by_machine: dict[str, _MachineParts] = {}

    for machine in machines:
        if use_shards:
            cat_m = shard_cat[shard_cat["machine_name"] == machine]
            cat_m = cat_m.sort_values("range_start_ts")
            boundary = cat_m["range_end_ts"].max() if not cat_m.empty else None
            if verbose:
                print(f"  {machine}: {len(cat_m)} shards"
                      f"{'' if boundary is None else f' sealed through {boundary}'}"
                      ", building fresh tail ... ", end="", flush=True)
            fresh = _build_fresh(engine, machine, boundary, runs_df, use_truth_json)
            if verbose:
                print(f"{len(fresh):,} fresh rows")
            parts_by_machine[machine] = _MachineParts(
                machine, list(cat_m["shard_path"]), fresh)
            manifest["shards"] += [
                {"id": int(r.id), "machine": machine, "path": r.shard_path,
                 "rows": int(r.row_count),
                 "range": [str(r.range_start_ts), str(r.range_end_ts)]}
                for r in cat_m.itertuples()
            ]
            manifest["fresh"][machine] = {
                "boundary": str(boundary), "rows": int(len(fresh)),
            }
        else:
            db_rows = _db_row_count(engine, machine)

            def _loader(m=machine, n=db_rows):
                df = _load_cached(m, n)
                if df is None:
                    if verbose:
                        print(f"  {m}: building feature cache from raw ...")
                    df = _build_and_cache(engine, m, runs_df, use_truth_json, n)
                return df

            parts_by_machine[machine] = _MachineParts(machine, [], None, _loader)

    # ── Pass 1: collect (ts, label), compute cuts, masks, split sizes ────────
    if verbose:
        print("\nPass 1 -- collect meta & compute split masks ...")

    meta_by_machine: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    ts_min = None
    ts_max = None
    label_counts: dict[str, int] = {}

    for machine, parts in parts_by_machine.items():
        ts_np, labels = parts.meta()
        if len(ts_np) == 0:
            continue
        y_np = _encode(labels, le)
        meta_by_machine[machine] = (ts_np, y_np)
        m_min, m_max = ts_np.min(), ts_np.max()
        ts_min = m_min if ts_min is None else min(ts_min, m_min)
        ts_max = m_max if ts_max is None else max(ts_max, m_max)
        for cls, cnt in labels.value_counts().items():
            label_counts[str(cls)] = label_counts.get(str(cls), 0) + int(cnt)

    if not meta_by_machine:
        raise RuntimeError("No feature rows from any machine -- nothing to train on.")

    ts_min = pd.Timestamp(ts_min); ts_max = pd.Timestamp(ts_max)
    span      = (ts_max - ts_min).total_seconds()
    gap       = timedelta(hours=cfg.GAP_HOURS)
    cut_train = ts_min + timedelta(seconds=span * cfg.TRAIN_FRAC)
    cut_val   = ts_min + timedelta(seconds=span * cfg.VAL_FRAC)

    if verbose:
        print(f"  Timeline : {ts_min}  ->  {ts_max}")
        print(f"  Train cut: {cut_train}")
        print(f"  Val   cut: {cut_val}")

    n_train = n_val = n_test = 0
    split_masks: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

    for machine, (ts_np, y_np) in meta_by_machine.items():
        ts_s  = pd.Series(ts_np)
        tr_m  = (ts_s < cut_train).to_numpy()
        va_m  = ((ts_s >= cut_train + gap) & (ts_s < cut_val)).to_numpy()

        not_trainval  = ~tr_m & ~va_m
        candidate_idx = np.where(not_trainval)[0]
        y_candidate   = y_np[candidate_idx]

        sub_rng  = np.random.default_rng(_RNG_SEED + hash(machine) % (2**31))
        sub_mask = _stratified_test_mask(y_candidate, sub_rng)
        te_m     = np.zeros(len(ts_np), dtype=bool)
        te_m[candidate_idx[sub_mask]] = True

        split_masks[machine] = (tr_m, va_m, te_m)
        n_train += int(tr_m.sum()); n_val += int(va_m.sum()); n_test += int(te_m.sum())

        if verbose:
            print(f"  {machine}: {len(ts_np):,} rows  "
                  f"(train={tr_m.sum():,} val={va_m.sum():,} test={te_m.sum():,})")

    total = sum(label_counts.values())
    if verbose:
        print(f"\nTotal feature rows: {total:,}")
        print("Label distribution:")
        for cls in cfg.CLASS_NAMES:
            cnt = label_counts.get(cls, 0)
            print(f"  {cls:15s}: {cnt:>8,}  ({cnt/max(total,1)*100:.1f}%)")
        print(f"\nSplit sizes: train={n_train:,}  val={n_val:,}  test={n_test:,}")

    if n_train == 0:
        raise RuntimeError("No training rows -- check split boundaries and data.")

    manifest["row_counts"] = {"total": total, "train": n_train,
                              "val": n_val, "test": n_test}
    manifest["label_counts"] = label_counts
    manifest["timeline"] = [str(ts_min), str(ts_max)]

    # ── Pass 2: pre-allocate arrays, fill part-by-part ────────────────────────
    if verbose:
        print("\nPass 2 -- filling split arrays ...")

    X_train = np.empty((n_train, n_feats), dtype=np.float32)
    X_val   = np.empty((n_val,   n_feats), dtype=np.float32)
    X_test  = np.empty((n_test,  n_feats), dtype=np.float32)
    y_train = np.empty(n_train, dtype=np.int32)
    y_val   = np.empty(n_val,   dtype=np.int32)
    y_test  = np.empty(n_test,  dtype=np.int32)
    g_train = np.empty(n_train, dtype=object)
    g_val   = np.empty(n_val,   dtype=object)
    g_test  = np.empty(n_test,  dtype=object)

    meta_parts: list[pd.DataFrame] = []
    ptr_tr = ptr_v = ptr_te = 0

    for machine, parts in parts_by_machine.items():
        if machine not in split_masks:
            continue
        tr_m, va_m, te_m = split_masks[machine]
        offset = 0

        for frame in parts.iter_frames():
            k = len(frame)
            if k == 0:
                continue
            f_tr = tr_m[offset:offset+k]
            f_va = va_m[offset:offset+k]
            f_te = te_m[offset:offset+k]

            X_np  = frame[feat_cols].to_numpy(dtype=np.float32)
            y_np  = _encode(frame["label"], le)
            sid   = frame["session_id"].to_numpy(dtype=object)
            ts_np = pd.to_datetime(frame["ts"]).to_numpy()
            mn_np = frame["machine_name"].to_numpy(dtype=object)

            def _fill(mask, X_buf, y_buf, g_buf, ptr):
                kk = int(mask.sum())
                if kk == 0:
                    return ptr
                X_buf[ptr:ptr+kk] = X_np[mask]
                y_buf[ptr:ptr+kk] = y_np[mask]
                g_buf[ptr:ptr+kk] = sid[mask]
                return ptr + kk

            ptr_tr = _fill(f_tr, X_train, y_train, g_train, ptr_tr)
            ptr_v  = _fill(f_va, X_val,   y_val,   g_val,   ptr_v)
            ptr_te = _fill(f_te, X_test,  y_test,  g_test,  ptr_te)

            if f_te.any():
                meta_parts.append(pd.DataFrame({
                    "ts":           ts_np[f_te],
                    "machine_name": mn_np[f_te],
                    "session_id":   sid[f_te],
                }))

            offset += k
            del frame, X_np, y_np, sid, ts_np, mn_np

        expected = len(meta_by_machine[machine][0])
        if offset != expected:
            raise RuntimeError(
                f"{machine}: pass-2 row count {offset} != pass-1 count {expected} "
                "(shard set changed mid-run?)")

    meta_test = (
        pd.concat(meta_parts, ignore_index=True)
        if meta_parts else
        pd.DataFrame(columns=["ts", "machine_name", "session_id"])
    )

    if verbose:
        print("Done.")

    return dict(
        X_train=X_train, y_train=y_train, groups_train=g_train,
        X_val=X_val,     y_val=y_val,     groups_val=g_val,
        X_test=X_test,   y_test=y_test,   groups_test=g_test,
        feature_columns=feat_cols,
        label_encoder=le,
        meta_test=meta_test,
        manifest=manifest,
    )
