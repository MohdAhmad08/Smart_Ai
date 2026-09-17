"""Label assignment -- two strategies depending on data availability.

Strategy A (preferred): use machine_runs failure_ts events (two-pointer O(N+M)).
Strategy B (fallback):  parse truth_json health column from machine_readings.
    A reading gets label=component when that component's health drops below
    HEALTH_FAIL_THRESHOLD within the next H_SECONDS of sim time.

build_labels() auto-selects: if runs_df is empty it falls through to strategy B.
"""
from __future__ import annotations

import json as _json

import numpy as np
import pandas as pd

# Import from config; fallback avoids circular import
try:
    from ml.config import HEALTH_FAIL_THRESHOLD
except ImportError:
    HEALTH_FAIL_THRESHOLD = 88.0

# Components tracked in truth_json (must match ml.config.CLASS_NAMES minus "none")
_COMPONENTS = ["bearing", "steam_valve", "heater", "water_pump"]


# ── Strategy A: machine_runs two-pointer ──────────────────────────────────────

def _labels_from_runs(
    readings_df: pd.DataFrame,
    runs_df: pd.DataFrame,
    H_seconds: float,
) -> pd.Series:
    H_ns = int(H_seconds * 1e9)
    all_parts: list[pd.Series] = []

    for machine in readings_df["machine_name"].unique():
        m_reads = readings_df[readings_df["machine_name"] == machine].sort_values("ts")
        m_fails = (
            runs_df[
                (runs_df["machine_name"] == machine)
                & runs_df["failure_ts"].notna()
            ]
            .sort_values("failure_ts")
        )

        idx_arr = m_reads.index.to_numpy()
        read_ts = m_reads["ts"].to_numpy(dtype="datetime64[ns]")

        if m_fails.empty:
            all_parts.append(pd.Series("none", index=idx_arr, dtype=object))
            continue

        fail_ts   = m_fails["failure_ts"].to_numpy(dtype="datetime64[ns]")
        fail_comp = m_fails["component"].to_numpy(dtype=object)
        labels = np.full(len(read_ts), "none", dtype=object)
        j = 0

        for i, rts in enumerate(read_ts):
            while j < len(fail_ts) and fail_ts[j] < rts:
                j += 1
            if j < len(fail_ts):
                diff_ns = int((fail_ts[j] - rts).astype("int64"))
                if diff_ns <= H_ns:
                    labels[i] = fail_comp[j]

        all_parts.append(pd.Series(labels, index=idx_arr, dtype=object))

    if not all_parts:
        return pd.Series(dtype=object, index=readings_df.index)
    return pd.concat(all_parts).reindex(readings_df.index)


# ── Strategy B: truth_json health-based labels (vectorized) ──────────────────

def _extract_health_arrays(json_col: np.ndarray) -> dict[str, np.ndarray]:
    """Parse truth_json column into per-component health arrays.

    Uses orjson if available (10x faster), otherwise stdlib json.
    Health values default to 100.0 for missing/null rows.
    """
    n = len(json_col)
    health: dict[str, np.ndarray] = {c: np.full(n, 100.0, dtype=np.float32) for c in _COMPONENTS}

    try:
        import orjson
        loads = orjson.loads
    except ImportError:
        loads = _json.loads

    for i, raw in enumerate(json_col):
        if raw is None:
            continue
        try:
            obj = loads(raw) if isinstance(raw, (str, bytes)) else raw
            h = obj.get("health", {})
            for comp in _COMPONENTS:
                v = h.get(comp)
                if v is not None:
                    health[comp][i] = float(v)
        except Exception:
            pass

    return health


def build_labels_from_truth_json(
    readings_df: pd.DataFrame,
    H_seconds: float,
    health_threshold: float = HEALTH_FAIL_THRESHOLD,
) -> pd.Series:
    """Derive labels from truth_json embedded in readings.

    For each machine: for each component, find where health first drops below
    health_threshold, then back-label all readings within H_seconds before that
    point as that component.  Repeats for successive degradation events.

    Parameters
    ----------
    readings_df      : columns [machine_name, ts, truth_json].
    H_seconds        : prediction horizon in sim seconds.
    health_threshold : health (0-100) below which = "degraded".
    """
    if "truth_json" not in readings_df.columns:
        raise ValueError("readings_df must contain 'truth_json' column for strategy B")

    H_ns = np.int64(H_seconds * 1e9)
    all_parts: list[pd.Series] = []

    for machine, mdf in readings_df.groupby("machine_name"):
        mdf = mdf.sort_values("ts").reset_index(drop=True)
        orig_index = (
            readings_df[readings_df["machine_name"] == machine]
            .sort_values("ts")
            .index
        )

        ts_ns  = mdf["ts"].to_numpy(dtype="datetime64[ns]").view(np.int64)
        n      = len(mdf)
        labels = np.full(n, "none", dtype=object)

        health = _extract_health_arrays(mdf["truth_json"].to_numpy())

        for comp in _COMPONENTS:
            h_arr = health[comp]
            below = h_arr < health_threshold   # boolean mask

            i = 0
            while i < n:
                # Find next index where health crosses below threshold
                nz = np.nonzero(below[i:])[0]
                if len(nz) == 0:
                    break
                fail_idx = i + nz[0]
                fail_ts_ns = ts_ns[fail_idx]

                # Back-label: all rows in [fail_ts - H, fail_ts] that are still "none"
                window_start_ns = fail_ts_ns - H_ns
                # Binary search for left boundary
                left = np.searchsorted(ts_ns, window_start_ns, side="left")
                for k in range(left, fail_idx + 1):
                    if labels[k] == "none":
                        labels[k] = comp

                # Advance past this degradation event: skip while still below threshold
                i = fail_idx + 1
                while i < n and h_arr[i] < health_threshold:
                    i += 1

        all_parts.append(pd.Series(labels, index=orig_index, dtype=object))

    if not all_parts:
        return pd.Series(dtype=object, index=readings_df.index)
    return pd.concat(all_parts).reindex(readings_df.index)


# ── Public API ────────────────────────────────────────────────────────────────

def build_labels(
    readings_df: pd.DataFrame,
    runs_df: pd.DataFrame,
    H_seconds: float,
) -> pd.Series:
    """Assign labels. Uses machine_runs if populated, else falls back to truth_json."""
    if runs_df is not None and len(runs_df) > 0:
        return _labels_from_runs(readings_df, runs_df, H_seconds)

    if "truth_json" not in readings_df.columns:
        return pd.Series("none", index=readings_df.index, dtype=object)

    return build_labels_from_truth_json(readings_df, H_seconds)
