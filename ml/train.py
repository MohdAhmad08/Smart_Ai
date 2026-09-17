"""Model training with checkpoint/resume support.

Usage
-----
  python -m ml.train           # train (resumes from checkpoint if one exists)
  python -m ml.train --reset   # delete checkpoint and start fresh
  python -m ml.train --tune    # run Optuna first, then train

How resume works
----------------
Every CHECKPOINT_ROUNDS rounds the booster is saved to
  ml/artifacts/checkpoint.json
  ml/artifacts/checkpoint_meta.json  (stores start_iteration + best_score)

On next run, if checkpoint.json exists:
  - Load the booster and continue from start_iteration
  - Reuse same data (cache is already warm)
  - Early stopping resets to count from the resumed best_score

Final artifact saved to ml/artifacts/model.json + metadata.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.utils.class_weight import compute_sample_weight

import ml.config as cfg
from ml.dataset import make_datasets
from ml.evaluate import evaluate_model

try:
    from xgboost import XGBClassifier, callback
    import xgboost as xgb
except ImportError:
    raise SystemExit("xgboost not installed -- run: pip install xgboost")

CHECKPOINT_ROUNDS = 25
_CKPT_MODEL = cfg.ARTIFACTS_DIR / "checkpoint.json"
_CKPT_META  = cfg.ARTIFACTS_DIR / "checkpoint_meta.json"


# ── Sample weights ────────────────────────────────────────────────────────────

def _sample_weights(y: np.ndarray) -> np.ndarray:
    return compute_sample_weight("balanced", y)


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def _save_checkpoint(booster, iteration: int, best_score: float, feat_cols: list[str]) -> None:
    cfg.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(_CKPT_MODEL))
    _CKPT_META.write_text(json.dumps({
        "start_iteration": iteration + 1,
        "best_score":      best_score,
        "feature_columns": feat_cols,
        "pipeline_version": cfg.PIPELINE_VERSION,
    }, indent=2))
    print(f"  [ckpt] saved at iteration {iteration}", flush=True)


def _load_checkpoint() -> tuple[xgb.Booster | None, int, float]:
    """Returns (booster_or_None, start_iteration, best_score)."""
    if not _CKPT_MODEL.exists() or not _CKPT_META.exists():
        return None, 0, np.inf
    try:
        meta = json.loads(_CKPT_META.read_text())
        if meta.get("pipeline_version") != cfg.PIPELINE_VERSION:
            print("  [ckpt] pipeline version mismatch -- ignoring checkpoint")
            return None, 0, np.inf
        booster = xgb.Booster()
        booster.load_model(str(_CKPT_MODEL))
        start = int(meta["start_iteration"])
        best  = float(meta["best_score"])
        print(f"  [ckpt] resuming from iteration {start}  (best_score={best:.6f})")
        return booster, start, best
    except Exception as e:
        print(f"  [ckpt] could not load checkpoint ({e}) -- starting fresh")
        return None, 0, np.inf


def _delete_checkpoint() -> None:
    for p in (_CKPT_MODEL, _CKPT_META):
        if p.exists():
            p.unlink()


# ── Custom checkpoint callback ────────────────────────────────────────────────

class _CheckpointCallback(xgb.callback.TrainingCallback):
    def __init__(self, every: int, feat_cols: list[str]):
        self.every     = every
        self.feat_cols = feat_cols
        self._best     = np.inf
        self._best_it  = 0

    def after_iteration(self, model, epoch: int, evals_log: dict) -> bool:
        # Track best val score
        try:
            score = list(list(evals_log.values())[0].values())[0][-1]
            if score < self._best:
                self._best    = score
                self._best_it = epoch
        except Exception:
            pass

        if (epoch + 1) % self.every == 0:
            _save_checkpoint(model, epoch, self._best, self.feat_cols)
        return False  # False = do not stop


# ── Training ──────────────────────────────────────────────────────────────────

def _subsample_train(X: np.ndarray, y: np.ndarray,
                     none_ratio: float = 2.0,
                     max_rows: int = 2_500_000) -> tuple[np.ndarray, np.ndarray]:
    """Keep ALL failure rows; cap 'none' rows to none_ratio × total failure rows.

    Preserves every failure example (the rare, valuable signal) while bounding
    the majority 'none' class so the DMatrix fits in RAM.  balanced sample
    weights (applied later) correct the residual imbalance.  If the result still
    exceeds max_rows, downsample 'none' further.
    """
    none_idx    = np.where(y == 0)[0]   # class 0 = "none"
    failure_idx = np.where(y != 0)[0]

    if len(failure_idx) == 0:
        return X, y

    none_cap = int(len(failure_idx) * none_ratio)
    # Respect the absolute row ceiling
    none_cap = min(none_cap, max_rows - len(failure_idx))
    none_cap = max(none_cap, len(failure_idx))  # never fewer none than failures

    rng = np.random.default_rng(42)
    if len(none_idx) > none_cap:
        none_keep = rng.choice(none_idx, size=none_cap, replace=False)
    else:
        none_keep = none_idx

    keep = np.concatenate([none_keep, failure_idx])
    rng.shuffle(keep)

    print(f"  Subsampling train: {len(X):,} -> {len(keep):,} rows "
          f"(none {len(none_idx):,}->{len(none_keep):,}, failures kept={len(failure_idx):,})")
    return X[keep], y[keep]


def _finalize_data(model, data: dict) -> None:
    """Score the val slice (kept for cost-aware threshold tuning in evaluate),
    compute the drift reference from the train distribution (Plan 03 A.2.5),
    then drop the large train/val arrays so evaluation runs lean."""
    from ml.feature_store import compute_ref_dist

    data["ref_dist"] = compute_ref_dist(data["X_train"], data["feature_columns"])
    counts = np.bincount(data["y_train"], minlength=cfg.N_CLASSES).astype(float)
    total  = max(counts.sum(), 1.0)
    data["class_base_rates"] = {
        cfg.CLASS_NAMES[i]: float(counts[i] / total) for i in range(cfg.N_CLASSES)
    }

    data["val_proba"] = model.predict_proba(data["X_val"])
    for k in ("X_train", "y_train", "X_val", "groups_train", "groups_val"):
        data.pop(k, None)


def train_model(tune_params: dict | None = None, reset: bool = False,
                use_checkpoint: bool = True, smoke: bool = False) -> tuple:
    t0 = time.time()
    print("\n" + "="*60)
    print("Phase 2 -- XGBoost Predictive Maintenance Training"
          + ("  [SMOKE]" if smoke else ""))
    print("="*60)

    if reset:
        _delete_checkpoint()
        print("  Checkpoint cleared.")

    data      = make_datasets(verbose=True)
    X_train   = data["X_train"]
    y_train   = data["y_train"]
    X_val     = data["X_val"]
    y_val     = data["y_val"]
    feat_cols = data["feature_columns"]

    # Subsample training set to fit in RAM
    X_train, y_train = _subsample_train(X_train, y_train)

    if smoke:
        X_train, y_train = X_train[::12], y_train[::12]
        print(f"  Smoke mode: train thinned to {len(X_train):,} rows")

    params = {**cfg.XGB_DEFAULTS, **(tune_params or {})}

    # Try to resume
    booster, start_iter, best_score = (_load_checkpoint() if use_checkpoint
                                       else (None, 0, np.inf))

    remaining = params["n_estimators"] - start_iter
    if remaining <= 0:
        print(f"  Already trained {start_iter} rounds -- loading checkpoint as final model.")
        model = XGBClassifier(**params)
        model._Booster = booster
        model.n_classes_ = cfg.N_CLASSES
        _finalize_data(model, data)
        return model, feat_cols, data

    print(f"\nTraining XGBoost  "
          f"(train={len(X_train):,}  val={len(X_val):,}  "
          f"features={len(feat_cols)}  "
          f"rounds={start_iter}->{params['n_estimators']})")

    sw = _sample_weights(y_train)
    ckpt_cb = _CheckpointCallback(every=CHECKPOINT_ROUNDS, feat_cols=feat_cols)

    if booster is not None:
        # Resume: use low-level xgb.train with xgb_model=booster
        dtrain = xgb.DMatrix(X_train, label=y_train, weight=sw)
        dval   = xgb.DMatrix(X_val,   label=y_val)

        del X_train, y_train, sw  # free before training loop

        raw_params = {k: v for k, v in params.items()
                      if k not in ("n_estimators", "early_stopping_rounds")}
        raw_params.setdefault("num_class", cfg.N_CLASSES)

        booster = xgb.train(
            raw_params,
            dtrain,
            num_boost_round=remaining,
            evals=[(dval, "validation_0")],
            xgb_model=booster,
            verbose_eval=50,
            callbacks=[ckpt_cb],
            early_stopping_rounds=cfg.EARLY_STOPPING_ROUNDS,
        )
        del dtrain, dval

        # Wrap in sklearn interface for compatibility
        model = XGBClassifier(**params)
        model._Booster    = booster
        model.n_classes_  = cfg.N_CLASSES
        model.best_iteration = booster.best_iteration if hasattr(booster, "best_iteration") else params["n_estimators"]

    else:
        # Fresh start with sklearn interface -- callbacks go in constructor
        model = XGBClassifier(
            **params,
            early_stopping_rounds=cfg.EARLY_STOPPING_ROUNDS,
            callbacks=[ckpt_cb],
        )
        model.fit(
            X_train, y_train,
            sample_weight=sw,
            eval_set=[(X_val, y_val)],
            verbose=50,
        )
        del X_train, y_train, X_val, y_val, sw

    _finalize_data(model, data)

    best_iter = getattr(model, "best_iteration", params["n_estimators"])
    print(f"\nBest iteration : {best_iter}")
    print(f"Training time  : {time.time() - t0:.1f}s")

    # Delete checkpoint on successful completion
    if use_checkpoint:
        _delete_checkpoint()

    return model, feat_cols, data


# ── Save final artifact ───────────────────────────────────────────────────────

def save_artifact(model, feat_cols: list[str], extra: dict | None = None,
                  out_dir: Path | None = None) -> None:
    out = Path(out_dir) if out_dir else cfg.ARTIFACTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    model_path = out / "model.json"
    model.save_model(str(model_path))

    meta = {
        "feature_columns":  feat_cols,
        "class_names":      cfg.CLASS_NAMES,
        "pipeline_version": cfg.PIPELINE_VERSION,
        "H_hours":          cfg.H_HOURS,
        "window_sizes":     cfg.WINDOW_SIZES,
        "nominal_speed":    cfg.NOMINAL_SPEED,
        "best_iteration":   int(getattr(model, "best_iteration", 0)),
    }
    if extra:
        meta.update({k: v for k, v in extra.items() if v is not None})
    (out / "metadata.json").write_text(json.dumps(meta, indent=2))

    print(f"\nArtifact saved  ->  {model_path}")
    print(f"Pipeline version: {cfg.PIPELINE_VERSION}")


# ── Optuna tuning ─────────────────────────────────────────────────────────────

def tune(X_train, y_train, X_val, y_val, n_trials: int = cfg.OPTUNA_TRIALS) -> dict:
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("optuna not installed -- skipping (pip install optuna)")
        return {}

    from sklearn.metrics import f1_score

    def objective(trial):
        p = {
            **cfg.XGB_DEFAULTS,
            "n_estimators":     trial.suggest_int("n_estimators", 100, 400),
            "max_depth":        trial.suggest_int("max_depth", 3, 7),
            "learning_rate":    trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample":        trial.suggest_float("subsample", 0.4, 0.8),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 0.8),
            "min_child_weight": trial.suggest_int("min_child_weight", 5, 30),
        }
        m = XGBClassifier(**p, early_stopping_rounds=20, verbosity=0)
        m.fit(X_train, y_train,
              sample_weight=_sample_weights(y_train),
              eval_set=[(X_val, y_val)], verbose=False)
        return f1_score(y_val, m.predict(X_val), average="macro", zero_division=0)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, timeout=cfg.OPTUNA_TIMEOUT, show_progress_bar=True)
    print(f"Best macro-F1 (val): {study.best_value:.4f}")
    print(f"Best params: {study.best_params}")
    return study.best_params


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune",    action="store_true")
    parser.add_argument("--trials",  type=int, default=cfg.OPTUNA_TRIALS)
    parser.add_argument("--no-eval", action="store_true")
    parser.add_argument("--reset",   action="store_true", help="Discard checkpoint and retrain from scratch")
    parser.add_argument("--no-mlflow", action="store_true",
                        help="Skip MLflow logging / registration / promotion")
    parser.add_argument("--smoke",   action="store_true",
                        help="Fast end-to-end pipeline test: thinned data, few "
                             "rounds, artifacts to a scratch dir, registers to "
                             "Staging but never auto-promotes")
    args = parser.parse_args()

    tune_params = {}
    if args.tune:
        print("Loading data for Optuna ...")
        d = make_datasets(verbose=False)
        tune_params = tune(d["X_train"], d["y_train"], d["X_val"], d["y_val"], args.trials)

    if args.smoke:
        tune_params = {**tune_params, "n_estimators": 12, "max_depth": 4}
        adir = cfg.ARTIFACTS_DIR / "smoke"
        adir.mkdir(parents=True, exist_ok=True)
    else:
        adir = cfg.ARTIFACTS_DIR

    model, feat_cols, data = train_model(
        tune_params or None, reset=args.reset,
        use_checkpoint=not args.smoke, smoke=args.smoke)

    extra = {
        "ref_dist":         data.pop("ref_dist", None),
        "class_base_rates": data.pop("class_base_rates", None),
        "trained_at":       time.strftime("%Y-%m-%d %H:%M:%S"),
        "smoke":            args.smoke or None,
    }
    save_artifact(model, feat_cols, extra=extra, out_dir=adir)

    summary = None
    if not args.no_eval:
        print("\n" + "="*60 + "\nEvaluation on test set\n" + "="*60)
        summary = evaluate_model(model, data["X_test"], data["y_test"],
                                 data["meta_test"], data["label_encoder"],
                                 y_val=data.get("y_val"), val_proba=data.get("val_proba"),
                                 artifacts_dir=adir)

    # ── MLflow: log run + register + champion/challenger (Plan 03 B/C) ───────
    if not args.no_mlflow and summary is not None:
        from ml.registry import log_training_run, promote_if_better

        run_id, version = log_training_run(
            artifacts_dir=adir,
            manifest=data.get("manifest"),
            extra_params={"smoke": args.smoke},
        )
        if args.smoke:
            print(f"Smoke run registered as {version} (Staging) — skipping promotion.")
        else:
            promote_if_better(
                version, model, summary.get("decision_thresholds"),
                data["X_test"], data["y_test"], artifacts_dir=adir)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    main()
