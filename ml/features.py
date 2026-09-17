"""Feature engineering -- used by BOTH training and live serving.

Memory strategy
---------------
Use pandas rolling (C-speed) for mean/std, numpy for slope.
Cast every intermediate result to float32 immediately.
Apply stride index *after* all rolling is done but *before* building
the final DataFrame, so peak RAM is:
  ~880 MB per machine (float32, 92 cols x 2.4M rows)
instead of 1.66 GB (float64).

Public API
----------
build_features_for_machine(machine_df, cfg) -> pd.DataFrame
build_feature_row(window_df, cfg) -> dict
get_feature_columns(cfg) -> list[str]
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _build_column_list(cfg) -> list[str]:
    cols: list[str] = []
    for sensor in cfg.SENSOR_COLS:
        for w in cfg.WINDOW_SIZES:
            cols += [
                f"{sensor}_w{w}_mean",
                f"{sensor}_w{w}_std",
                f"{sensor}_w{w}_slope",
            ]
    cols += [
        "current_per_speed",
        "power_per_speed",
        "vib_per_current",
        "sf_per_speed",
        "wat_per_speed",
        "sf_tot_rate",
        "wat_tot_rate",
        "em_energy_rate",
        "reject_pct",
        "is_running",
        "machine_time_h",
    ]
    return cols


def build_features_for_machine(machine_df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Vectorised feature computation.  Returns strided rows only.

    Uses pandas rolling (C-speed), casts to float32 immediately after each
    computation, and builds the output dict column-by-column so the peak
    allocation is one column at a time rather than the full 92-column matrix.
    """
    df = machine_df.sort_values("ts").reset_index(drop=True)
    n  = len(df)

    valid_start = cfg.MAX_WINDOW - 1
    stride_idx  = np.arange(valid_start, n, cfg.FEATURE_STRIDE_READINGS)
    ns = len(stride_idx)
    if ns == 0:
        return pd.DataFrame()

    # Build output arrays keyed by column name -- strided length only
    out: dict[str, np.ndarray] = {}

    for sensor in cfg.SENSOR_COLS:
        # float32 series; ffill then 0-fill
        col = df[sensor].astype("float32").ffill().fillna(0.0)

        for w in cfg.WINDOW_SIZES:
            mp = max(2, w // 4)
            r  = col.rolling(window=w, min_periods=mp)

            # mean
            arr = r.mean().fillna(0.0).to_numpy(dtype=np.float32)
            out[f"{sensor}_w{w}_mean"] = arr[stride_idx]
            del arr

            # std
            arr = r.std().fillna(0.0).to_numpy(dtype=np.float32)
            out[f"{sensor}_w{w}_std"] = arr[stride_idx]
            del arr

            # slope: (col[i] - col[i-(w-1)]) / (w-1)
            col_np = col.to_numpy(dtype=np.float32)
            slope  = np.zeros(n, dtype=np.float32)
            slope[w-1:] = (col_np[w-1:] - col_np[:n-(w-1)]) / max(w - 1, 1)
            out[f"{sensor}_w{w}_slope"] = slope[stride_idx]
            del slope, col_np

        del col

    # Cross-sensor ratios -- only at stride positions
    def _col_f32(name, clip_lo=None):
        a = df[name].to_numpy(dtype=np.float32)
        np.nan_to_num(a, nan=0.0, copy=False)
        if clip_lo is not None:
            np.clip(a, clip_lo, None, out=a)
        return a[stride_idx]

    speed = _col_f32("speed", clip_lo=0.5)
    mc    = _col_f32("motor_current", clip_lo=0.01)
    vib   = _col_f32("vibration_rms")
    em    = _col_f32("em_power")
    sf    = _col_f32("sf_flow")
    wat   = _col_f32("wat_flow")

    out["current_per_speed"] = mc  / speed
    out["power_per_speed"]   = em  / speed
    out["vib_per_current"]   = vib / mc
    out["sf_per_speed"]      = sf  / speed
    out["wat_per_speed"]     = wat / speed

    # Totalizer rates
    w0 = cfg.WINDOW_SIZES[0]
    for tot_col, rate_key in [
        ("sf_tot",    "sf_tot_rate"),
        ("wat_tot",   "wat_tot_rate"),
        ("em_energy", "em_energy_rate"),
    ]:
        tot = df[tot_col].astype("float32").ffill().fillna(0.0)
        tot_np = tot.to_numpy(dtype=np.float32)
        rate   = np.zeros(n, dtype=np.float32)
        rate[w0:] = (tot_np[w0:] - tot_np[:n-w0]) / w0
        out[rate_key] = rate[stride_idx]
        del tot, tot_np, rate

    # Quality
    good   = df["good_count"].to_numpy(dtype=np.float32)
    reject = df["reject_count"].to_numpy(dtype=np.float32)
    np.nan_to_num(good,   nan=0.0, copy=False)
    np.nan_to_num(reject, nan=0.0, copy=False)
    denom = np.clip(good + reject, 1.0, None)
    out["reject_pct"] = (reject / denom)[stride_idx]

    out["is_running"]     = (df["state"].to_numpy() == "running").astype(np.float32)[stride_idx]
    mt = df["machine_time_s"].to_numpy(dtype=np.float32)
    np.nan_to_num(mt, nan=0.0, copy=False)
    out["machine_time_h"] = (mt / 3600.0)[stride_idx]

    # Assemble numeric features -- only strided rows, all float32
    feat_df = pd.DataFrame(out)

    # Metadata: extract as plain Python lists to avoid Arrow string allocation
    feat_df["session_id"]   = list(df["session_id"].to_numpy()[stride_idx])
    feat_df["machine_name"] = list(df["machine_name"].to_numpy()[stride_idx])
    feat_df["ts"]           = df["ts"].to_numpy()[stride_idx]
    feat_df["seq"]          = df["seq"].to_numpy(dtype=np.int32)[stride_idx]

    return feat_df.reset_index(drop=True)


def build_feature_row(window_df: pd.DataFrame, cfg) -> dict:
    """One feature dict from a trailing window (serving time)."""
    result = build_features_for_machine(window_df, cfg)
    if result.empty:
        return {}
    last = result.iloc[-1]
    return {c: float(last[c]) for c in _build_column_list(cfg) if c in last.index}


def get_feature_columns(cfg) -> list[str]:
    return _build_column_list(cfg)
