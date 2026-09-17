"""Model evaluation — confusion matrix, per-class metrics, lead-time, SHAP, baselines.

Can be run standalone after training:
  python -m ml.evaluate

Or called from train.py automatically.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import ml.config as cfg

# F-beta used when tuning decision thresholds: beta=2 weights recall 4x over
# precision — a missed failure costs far more than a false alarm (Plan 02 B.7).
THRESHOLD_BETA = 2.0


# ── Cost-aware decision thresholds (Plan 02 B.7) ─────────────────────────────

def tune_thresholds(
    y_val: np.ndarray,
    val_proba: np.ndarray,
    beta: float = THRESHOLD_BETA,
) -> dict[str, float]:
    """Pick a per-failure-class probability threshold on the VALIDATION set.

    One-vs-rest: for each failure class, sweep the PR curve and keep the
    threshold that maximizes F-beta.  Classes absent from val fall back to 0.5.
    """
    from sklearn.metrics import precision_recall_curve

    thresholds: dict[str, float] = {}
    for i, cls in enumerate(cfg.CLASS_NAMES):
        if cls == "none":
            continue
        y_bin = (np.asarray(y_val) == i).astype(int)
        if y_bin.sum() == 0:
            thresholds[cls] = 0.5
            continue
        prec, rec, thr = precision_recall_curve(y_bin, val_proba[:, i])
        prec, rec = prec[:-1], rec[:-1]          # last PR point has no threshold
        denom = beta**2 * prec + rec
        fbeta = np.where(denom > 0, (1 + beta**2) * prec * rec / np.where(denom == 0, 1.0, denom), 0.0)
        thresholds[cls] = float(thr[int(fbeta.argmax())])
    return thresholds


def apply_thresholds(proba: np.ndarray, thresholds: dict[str, float]) -> np.ndarray:
    """Cost-aware decision rule — shared by evaluation AND live serving.

    A failure class fires when its probability exceeds its threshold; if several
    fire, the one furthest above its threshold (p/thr) wins; else "none".
    Assumes cfg.CLASS_NAMES[0] == "none".
    """
    proba = np.asarray(proba)
    thr = np.array([float(thresholds.get(c, 0.5)) for c in cfg.CLASS_NAMES[1:]])
    thr = np.maximum(thr, 1e-9)
    ratios = proba[:, 1:] / thr
    return np.where(ratios.max(axis=1) >= 1.0, ratios.argmax(axis=1) + 1, 0).astype(int)


def evaluate_model(
    model,
    X_test: np.ndarray,
    y_test: np.ndarray,
    meta_test: pd.DataFrame,
    label_encoder=None,
    save_plots: bool = True,
    y_val: np.ndarray | None = None,
    val_proba: np.ndarray | None = None,
    artifacts_dir: Path | str | None = None,
) -> dict:
    """Compute and print all evaluation metrics.  Returns a summary dict."""
    from sklearn.metrics import (
        classification_report, confusion_matrix, f1_score,
        precision_recall_curve, average_precision_score,
    )

    class_names = cfg.CLASS_NAMES
    adir = Path(artifacts_dir) if artifacts_dir else cfg.ARTIFACTS_DIR
    pdir = adir / "plots"
    pdir.mkdir(parents=True, exist_ok=True)

    # ── Predictions ──────────────────────────────────────────────────────────
    y_pred_proba  = model.predict_proba(X_test)
    y_pred_argmax = y_pred_proba.argmax(axis=1)
    macro_f1_argmax = f1_score(y_test, y_pred_argmax, average="macro", zero_division=0)

    # ── Cost-aware operating point (thresholds tuned on the val set) ─────────
    thresholds: dict[str, float] | None = None
    if y_val is not None and val_proba is not None:
        thresholds = tune_thresholds(y_val, val_proba)
        y_pred     = apply_thresholds(y_pred_proba, thresholds)
        print("\n── Cost-aware thresholds (tuned on val, F-beta=%.0f) ──────────────"
              % THRESHOLD_BETA)
        for cls, t in thresholds.items():
            print(f"  {cls:15s}: p >= {t:.4f}")
    else:
        y_pred = y_pred_argmax
        print("\n(no validation predictions supplied — using argmax decision rule)")

    # ── Classification report ─────────────────────────────────────────────────
    report = classification_report(
        y_test, y_pred,
        labels=list(range(len(class_names))),
        target_names=class_names,
        zero_division=0,
        output_dict=True,
    )
    macro_f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)

    print("\n── Classification Report (operating point) ────────────────────────")
    print(classification_report(
        y_test, y_pred,
        labels=list(range(len(class_names))),
        target_names=class_names,
        zero_division=0,
    ))
    if thresholds is not None:
        print(f"  macro-F1 argmax      : {macro_f1_argmax:.4f}")
        print(f"  macro-F1 cost-aware  : {macro_f1:.4f}")

    # ── Confusion matrix ─────────────────────────────────────────────────────
    cm = confusion_matrix(y_test, y_pred, labels=list(range(len(class_names))))
    print("── Confusion Matrix ───────────────────────────────────────────────")
    header = f"{'':>15s}" + "".join(f"{c:>14s}" for c in class_names)
    print(header)
    for i, row in enumerate(cm):
        print(f"{class_names[i]:>15s}" + "".join(f"{v:>14d}" for v in row))

    # ── Baseline comparison ───────────────────────────────────────────────────
    y_always_none = np.zeros_like(y_test)  # always predict class 0 = "none"
    baseline_f1   = f1_score(y_test, y_always_none, average="macro", zero_division=0)
    print(f"\n── Baseline vs Model ──────────────────────────────────────────────")
    print(f"  'Always none' macro-F1  : {baseline_f1:.4f}")
    print(f"  Model        macro-F1   : {macro_f1:.4f}  "
          f"({'BEATS' if macro_f1 > baseline_f1 else 'WORSE THAN'} baseline)")

    # ── Per-class PR-AUC ─────────────────────────────────────────────────────
    print("\n── Per-class Average Precision (PR-AUC) ───────────────────────────")
    pr_aucs = {}
    for i, cls in enumerate(class_names):
        y_bin   = (y_test == i).astype(int)
        ap      = average_precision_score(y_bin, y_pred_proba[:, i], pos_label=1)
        pr_aucs[cls] = float(ap)
        print(f"  {cls:15s}: AP = {ap:.4f}")

    # ── Lead-time analysis ────────────────────────────────────────────────────
    print("\n── Lead-Time Analysis (hours before failure correctly predicted) ────")
    lead_time_results = _lead_time_analysis(
        y_test, y_pred, meta_test, class_names
    )
    for cls, stats in lead_time_results.items():
        if stats:
            print(f"  {cls:15s}: median={stats['median_h']:.1f}h  "
                  f"mean={stats['mean_h']:.1f}h  n={stats['n']}")

    # ── SHAP (optional) ───────────────────────────────────────────────────────
    _try_shap(model, X_test, cfg, save_plots, plots_dir=pdir)

    # ── Save confusion matrix plot ─────────────────────────────────────────────
    if save_plots:
        _save_cm_plot(cm, class_names, plots_dir=pdir)

    summary = {
        "macro_f1":          float(macro_f1),
        "macro_f1_argmax":   float(macro_f1_argmax),
        "baseline_macro_f1": float(baseline_f1),
        "decision_thresholds": thresholds,
        "threshold_beta":    THRESHOLD_BETA if thresholds else None,
        "per_class":         {cls: report[cls] for cls in class_names if cls in report},
        "pr_auc":            pr_aucs,
        "lead_time":         lead_time_results,
        "pipeline_version":  cfg.PIPELINE_VERSION,
    }

    # Save summary JSON
    summary_path = adir / "eval_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nEval summary saved to: {summary_path}")

    # Persist thresholds into metadata.json so live serving uses the same rule
    if thresholds is not None:
        meta_path = adir / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            meta["decision_thresholds"] = thresholds
            meta["threshold_beta"]      = THRESHOLD_BETA
            meta_path.write_text(json.dumps(meta, indent=2))
            print(f"Thresholds saved into: {meta_path}")

    return summary


# ── Lead-time helper ──────────────────────────────────────────────────────────

def _lead_time_analysis(
    y_test: np.ndarray,
    y_pred: np.ndarray,
    meta_test: pd.DataFrame,
    class_names: list[str],
) -> dict:
    """For each true failure class, how far ahead did the model raise that class?"""
    results = {}

    meta = meta_test.reset_index(drop=True)
    if len(meta) != len(y_test):
        return {}

    # Load failure events to get actual failure_ts
    try:
        from ml.db import get_engine, load_runs
        runs = load_runs(get_engine())
    except Exception:
        return {}

    for cls_idx, cls_name in enumerate(class_names):
        if cls_name == "none":
            continue

        # Rows where true label == cls AND prediction == cls
        correct_mask = (y_test == cls_idx) & (y_pred == cls_idx)
        if not correct_mask.any():
            results[cls_name] = None
            continue

        correct_rows = meta[correct_mask].copy()
        correct_rows["ts"] = pd.to_datetime(correct_rows["ts"])

        lead_hours: list[float] = []
        for machine in correct_rows["machine_name"].unique():
            m_rows  = correct_rows[correct_rows["machine_name"] == machine]
            m_fails = runs[
                (runs["machine_name"] == machine)
                & (runs["component"] == cls_name)
                & runs["failure_ts"].notna()
            ].sort_values("failure_ts")

            for _, row in m_rows.iterrows():
                t_pred = row["ts"]
                future = m_fails[m_fails["failure_ts"] >= t_pred]
                if not future.empty:
                    diff_h = (future.iloc[0]["failure_ts"] - t_pred).total_seconds() / 3600.0
                    lead_hours.append(float(diff_h))

        if lead_hours:
            arr = np.array(lead_hours)
            results[cls_name] = {
                "n":        len(arr),
                "median_h": float(np.median(arr)),
                "mean_h":   float(np.mean(arr)),
                "p25_h":    float(np.percentile(arr, 25)),
                "p75_h":    float(np.percentile(arr, 75)),
            }
        else:
            results[cls_name] = None

    return results


# ── SHAP (optional) ───────────────────────────────────────────────────────────

def _try_shap(model, X_test: np.ndarray, cfg, save_plots: bool,
              plots_dir: Path | None = None) -> None:
    try:
        import shap
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(shap / matplotlib not installed — skipping SHAP; pip install shap matplotlib)")
        return
    plots_dir = plots_dir or cfg.PLOTS_DIR

    print("\n── SHAP Feature Importance ────────────────────────────────────────")
    explainer = shap.TreeExplainer(model)
    sample_n  = min(2000, len(X_test))
    shap_vals = explainer.shap_values(X_test[:sample_n])

    feature_cols = [c.replace("_", " ") for c in get_feature_columns(cfg)]
    n_feats = len(feature_cols)

    def _vals_for_class(cls_idx: int) -> np.ndarray:
        """Return (n_samples, n_features) SHAP matrix for one class.

        Handles both return shapes:
          - list of per-class arrays  (older shap)
          - single 3D array (n_samples, n_features, n_classes)  (newer shap)
          - single 2D array (binary / single output)
        """
        if isinstance(shap_vals, list):
            return np.asarray(shap_vals[cls_idx])
        arr = np.asarray(shap_vals)
        if arr.ndim == 3:                 # (samples, features, classes)
            return arr[:, :, cls_idx]
        return arr                        # (samples, features)

    if save_plots:
        # Console: top features overall (mean |SHAP| across all classes)
        all_mean = np.zeros(n_feats, dtype=float)
        for cls_idx in range(len(cfg.CLASS_NAMES)):
            all_mean += np.abs(_vals_for_class(cls_idx)).mean(axis=0)
        order = np.argsort(all_mean)[::-1][:15]
        print("  Top 15 features (mean |SHAP|, all classes):")
        for rank, i in enumerate(order, 1):
            print(f"    {rank:2d}. {feature_cols[int(i)]:28s} {all_mean[int(i)]:.4f}")

        for cls_idx, cls_name in enumerate(cfg.CLASS_NAMES):
            mean_abs = np.abs(_vals_for_class(cls_idx)).mean(axis=0)  # (n_features,)
            top_k    = 15
            top_idx  = np.argsort(mean_abs)[-top_k:]                   # ascending
            names    = [feature_cols[int(i)] for i in top_idx]
            heights  = [float(mean_abs[int(i)]) for i in top_idx]

            fig, ax = plt.subplots(figsize=(8, 5))
            ax.barh(names, heights)
            ax.set_title(f"SHAP -- {cls_name}")
            ax.set_xlabel("|SHAP value|")
            fig.tight_layout()
            out = plots_dir / f"shap_{cls_name}.png"
            fig.savefig(out, dpi=100)
            plt.close(fig)
            print(f"  Saved: {out}")


# ── Confusion matrix plot ──────────────────────────────────────────────────────

def _save_cm_plot(cm: np.ndarray, class_names: list[str],
                  plots_dir: Path | None = None) -> None:
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
    except ImportError:
        return
    plots_dir = plots_dir or cfg.PLOTS_DIR

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    plt.colorbar(im, ax=ax)
    ax.set(
        xticks=range(len(class_names)), yticks=range(len(class_names)),
        xticklabels=class_names, yticklabels=class_names,
        xlabel="Predicted", ylabel="True",
        title="Confusion Matrix (test set)",
    )
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black")
    fig.tight_layout()
    out = plots_dir / "confusion_matrix.png"
    fig.savefig(out, dpi=100)
    plt.close(fig)
    print(f"  Confusion matrix saved: {out}")


# ── Standalone entry point ────────────────────────────────────────────────────

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from xgboost import XGBClassifier
    from ml.dataset import make_datasets
    from ml.features import get_feature_columns

    model_path = cfg.ARTIFACTS_DIR / "model.json"
    if not model_path.exists():
        raise SystemExit(f"No model found at {model_path} — run train.py first.")

    model = XGBClassifier()
    model.load_model(str(model_path))

    data = make_datasets(verbose=True)
    data.pop("X_train", None); data.pop("y_train", None)
    data.pop("groups_train", None); data.pop("groups_val", None)

    val_proba = model.predict_proba(data.pop("X_val"))

    evaluate_model(
        model,
        data["X_test"], data["y_test"],
        data["meta_test"],
        data["label_encoder"],
        y_val=data["y_val"],
        val_proba=val_proba,
    )


def get_feature_columns(cfg_module):
    from ml.features import get_feature_columns as _get
    return _get(cfg_module)


if __name__ == "__main__":
    main()
