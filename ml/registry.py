"""Registry glue — the single seam between MLflow, the MySQL model_registry
table, and the serving backend (Plan 03 Parts B + F).

Responsibilities
----------------
- log_training_run()      : log params/metrics/artifacts + dataset manifest to
                            MLflow, register the model, alias it "staging".
- promote_if_better()     : champion/challenger — evaluate both on the SAME
                            fresh holdout, promote only if the challenger beats
                            the champion by PROMOTE_MARGIN (Part B.3).
- promote()               : move the "production" alias, archive the old
                            champion, mirror to MySQL, back up the bundle.
- load_production_model() : what the backend serving loads (reads the MySQL
                            pointer + filesystem bundle — no MLflow needed at
                            serve time).
- current_model_summary() : registry row for /api/model/info.

Model binaries live in MLflow; `ml/model_store/<version>/` keeps a filesystem
backup that serving reads (Part F backup_to_store), and `model_registry` in
MySQL is the cheap dashboard pointer.

CLI
---
  python -m ml.registry --bootstrap   # register the existing ml/artifacts
                                      # bundle as the first Production model
  python -m ml.registry --status      # print registry state
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import text

import ml.config as cfg
from ml.db import get_engine
from ml.tables import ensure_tables

MODEL_NAME     = os.getenv("MLFLOW_MODEL_NAME", "machine-pdm")
EXPERIMENT     = os.getenv("MLFLOW_EXPERIMENT", "machine-pdm")
PROMOTE_MARGIN = float(os.getenv("PROMOTE_MARGIN", "0.005"))
PROMOTE_MODE   = os.getenv("PROMOTE_MODE", "auto")          # auto | manual
MODEL_STORE    = cfg.ML_ROOT / "model_store"

_DEF_TRACKING = "sqlite:///" + str(cfg.ML_ROOT / "mlflow.db").replace("\\", "/")
TRACKING_URI  = os.getenv("MLFLOW_TRACKING_URI", _DEF_TRACKING)


def _mlflow():
    """Import + configure mlflow lazily (serving must not require it)."""
    import mlflow
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)
    return mlflow


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fmt_dt(dt: datetime | None) -> str | None:
    return None if dt is None else dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# ── MLflow tracking + registration (Part B.1/B.2) ─────────────────────────────

def _flatten_metrics(eval_summary: dict) -> dict[str, float]:
    m: dict[str, float] = {}
    for k in ("macro_f1", "macro_f1_argmax", "baseline_macro_f1"):
        if eval_summary.get(k) is not None:
            m[k] = float(eval_summary[k])
    for cls, d in (eval_summary.get("per_class") or {}).items():
        for stat in ("precision", "recall", "f1-score"):
            if stat in d:
                m[f"{cls}_{stat.replace('-score','')}"] = float(d[stat])
    for cls, v in (eval_summary.get("pr_auc") or {}).items():
        m[f"{cls}_pr_auc"] = float(v)
    for cls, d in (eval_summary.get("lead_time") or {}).items():
        if d:
            m[f"{cls}_lead_median_h"] = float(d["median_h"])
    return m


def log_training_run(
    artifacts_dir: Path | str | None = None,
    manifest: dict | None = None,
    extra_params: dict | None = None,
    register: bool = True,
) -> tuple[str, str]:
    """Log a completed training run (bundle already on disk) to MLflow.

    Returns (run_id, version_str) — version_str like "v3", "" if not registered.
    """
    mlflow = _mlflow()
    from mlflow.tracking import MlflowClient

    adir = Path(artifacts_dir or cfg.ARTIFACTS_DIR)
    meta = json.loads((adir / "metadata.json").read_text())
    eval_summary = {}
    if (adir / "eval_summary.json").exists():
        eval_summary = json.loads((adir / "eval_summary.json").read_text())

    params = {
        "pipeline_version": meta.get("pipeline_version"),
        "H_hours":          meta.get("H_hours"),
        "window_sizes":     str(meta.get("window_sizes")),
        "n_features":       len(meta.get("feature_columns", [])),
        "best_iteration":   meta.get("best_iteration"),
        **{f"xgb_{k}": v for k, v in cfg.XGB_DEFAULTS.items()
           if isinstance(v, (int, float, str))},
        **(extra_params or {}),
    }

    with mlflow.start_run(run_name=f"train-{_now():%Y%m%d-%H%M%S}") as run:
        mlflow.log_params(params)
        metrics = _flatten_metrics(eval_summary)
        if metrics:
            mlflow.log_metrics(metrics)

        for fname in ("model.json", "metadata.json", "eval_summary.json"):
            p = adir / fname
            if p.exists():
                mlflow.log_artifact(str(p), artifact_path="model")
        plots = adir / "plots"
        if plots.exists():
            mlflow.log_artifacts(str(plots), artifact_path="plots")
        if manifest is not None:
            mlflow.log_dict(manifest, "dataset_manifest.json")

        run_id = run.info.run_id

    version_str = ""
    if register:
        client = MlflowClient()
        try:
            client.create_registered_model(MODEL_NAME)
        except Exception:
            pass  # already exists
        mv = client.create_model_version(
            name=MODEL_NAME,
            source=f"runs:/{run_id}/model",
            run_id=run_id,
        )
        version_str = f"v{mv.version}"
        try:
            client.set_registered_model_alias(MODEL_NAME, "staging", mv.version)
        except Exception:
            pass  # older mlflow without alias API

        _mirror_row(version_str, "Staging", meta, eval_summary, run_id,
                    artifact_path=str(MODEL_STORE / version_str))
        backup_to_store(version_str, adir)

    print(f"MLflow run {run_id} logged"
          + (f", registered {MODEL_NAME} {version_str} (staging)" if version_str else ""))
    return run_id, version_str


# ── Filesystem backup (Part F backup_to_store) ────────────────────────────────

def backup_to_store(version_str: str, artifacts_dir: Path | str | None = None) -> Path:
    adir = Path(artifacts_dir or cfg.ARTIFACTS_DIR)
    dest = MODEL_STORE / version_str
    dest.mkdir(parents=True, exist_ok=True)
    for fname in ("model.json", "metadata.json", "eval_summary.json"):
        src = adir / fname
        if src.exists():
            shutil.copy2(src, dest / fname)
    return dest


# ── MySQL mirror (dashboard pointer) ──────────────────────────────────────────

def _mirror_row(version_str: str, stage: str, meta: dict, eval_summary: dict,
                run_id: str | None, artifact_path: str,
                promoted: bool = False) -> None:
    engine = get_engine()
    ensure_tables(engine)
    key_metrics = {
        "macro_f1":          eval_summary.get("macro_f1"),
        "macro_f1_argmax":   eval_summary.get("macro_f1_argmax"),
        "baseline_macro_f1": eval_summary.get("baseline_macro_f1"),
        "per_class_recall":  {c: d.get("recall")
                              for c, d in (eval_summary.get("per_class") or {}).items()},
    }
    now = _now()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO model_registry
                (version, stage, pipeline_version, metrics, mlflow_run_id,
                 artifact_path, trained_at, promoted_at)
            VALUES (:v, :st, :pv, :m, :rid, :ap, :ta, :pa)
            ON DUPLICATE KEY UPDATE
                stage = :st, metrics = :m, artifact_path = :ap,
                promoted_at = COALESCE(:pa, promoted_at)
        """), {
            "v":  version_str, "st": stage,
            "pv": meta.get("pipeline_version"),
            "m":  json.dumps(key_metrics),
            "rid": run_id, "ap": artifact_path,
            "ta": _fmt_dt(now), "pa": _fmt_dt(now) if promoted else None,
        })


def mirror_to_registry(summary: dict) -> None:
    """Public wrapper kept for the Plan 03 Part F surface."""
    _mirror_row(summary["version"], summary.get("stage", "Staging"),
                summary.get("meta", {}), summary.get("eval_summary", {}),
                summary.get("run_id"), summary.get("artifact_path", ""),
                promoted=summary.get("stage") == "Production")


def _registry_rows(engine=None) -> list[dict]:
    engine = engine or get_engine()
    ensure_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT version, stage, pipeline_version, metrics, mlflow_run_id, "
            "artifact_path, trained_at, promoted_at FROM model_registry "
            "ORDER BY id DESC"
        )).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("metrics"), (str, bytes)):
            d["metrics"] = json.loads(d["metrics"])
        for k in ("trained_at", "promoted_at"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        out.append(d)
    return out


def production_row(engine=None) -> dict | None:
    for r in _registry_rows(engine):
        if r["stage"] == "Production":
            return r
    return None


# ── Promotion (Part B.3) ──────────────────────────────────────────────────────

def promote(version_str: str, artifacts_dir: Path | str | None = None) -> None:
    """Make version_str Production: MLflow alias + MySQL mirror + archive old."""
    engine = get_engine()
    ensure_tables(engine)
    old = production_row(engine)

    # MLflow alias (best-effort — registry of record, but serving uses MySQL)
    try:
        _mlflow()
        from mlflow.tracking import MlflowClient
        client = MlflowClient()
        num = int(version_str.lstrip("v"))
        client.set_registered_model_alias(MODEL_NAME, "production", num)
        if old and old["version"] != version_str:
            try:
                client.set_model_version_tag(
                    MODEL_NAME, old["version"].lstrip("v"), "archived", "true")
            except Exception:
                pass
    except Exception as e:
        print(f"  (mlflow alias update skipped: {e})")

    now = _now()
    with engine.begin() as conn:
        if old and old["version"] != version_str:
            conn.execute(text(
                "UPDATE model_registry SET stage='Archived' WHERE version=:v"),
                {"v": old["version"]})
        conn.execute(text(
            "UPDATE model_registry SET stage='Production', promoted_at=:p "
            "WHERE version=:v"), {"p": _fmt_dt(now), "v": version_str})

    if artifacts_dir is not None:
        backup_to_store(version_str, artifacts_dir)

    print(f"Promoted {version_str} to Production"
          + (f" (archived {old['version']})" if old and old["version"] != version_str else ""))


def _macro_f1_of(model, thresholds: dict | None, X_test, y_test) -> float:
    from sklearn.metrics import f1_score
    from ml.evaluate import apply_thresholds
    proba = model.predict_proba(X_test)
    y_pred = (apply_thresholds(proba, thresholds)
              if thresholds else proba.argmax(axis=1))
    return float(f1_score(y_test, y_pred, average="macro", zero_division=0))


def promote_if_better(
    candidate_version: str,
    candidate_model,
    candidate_thresholds: dict | None,
    X_test,
    y_test,
    artifacts_dir: Path | str | None = None,
    margin: float = PROMOTE_MARGIN,
) -> dict:
    """Champion/challenger on the SAME holdout (Part B.3).

    - No champion → promote (bootstrap).
    - PROMOTE_MODE=manual → never auto-promote; report the decision.
    - Otherwise promote iff challenger_f1 >= champion_f1 + margin.
    """
    champ = production_row()
    cand_f1 = _macro_f1_of(candidate_model, candidate_thresholds, X_test, y_test)

    if champ is None:
        promote(candidate_version, artifacts_dir)
        return {"decision": "promoted", "reason": "no existing Production model",
                "challenger_f1": cand_f1, "champion_f1": None}

    champ_f1 = None
    try:
        champ_model, champ_meta, _ = _load_bundle(Path(champ["artifact_path"]))
        champ_f1 = _macro_f1_of(champ_model, champ_meta.get("decision_thresholds"),
                                X_test, y_test)
    except Exception as e:
        print(f"  (could not evaluate champion on holdout: {e})")

    decision = {
        "challenger": candidate_version, "challenger_f1": cand_f1,
        "champion":   champ["version"],  "champion_f1":   champ_f1,
        "margin":     margin,
    }

    beats = champ_f1 is not None and cand_f1 >= champ_f1 + margin
    if PROMOTE_MODE == "manual":
        decision["decision"] = "manual_gate"
        decision["reason"] = (
            f"PROMOTE_MODE=manual — {'would' if beats else 'would NOT'} promote; "
            f"run: python -m ml.registry --promote {candidate_version}")
    elif beats:
        promote(candidate_version, artifacts_dir)
        decision["decision"] = "promoted"
    else:
        decision["decision"] = "kept_champion"
        decision["reason"] = "challenger did not beat champion by margin"

    print(f"Champion/challenger: {decision}")
    return decision


# ── Serving loader (used by backend prediction_service) ──────────────────────

def _load_bundle(bundle_dir: Path):
    """(XGBClassifier, metadata dict, version dir) from a model_store bundle."""
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(bundle_dir / "model.json"))
    meta = json.loads((bundle_dir / "metadata.json").read_text())
    return model, meta, bundle_dir


def load_production_model():
    """Returns (model, metadata, version_str) for the Production model, or
    None when no registry row / bundle exists (caller falls back to artifacts)."""
    row = production_row()
    if row is None:
        return None
    bundle = Path(row["artifact_path"])
    if not (bundle / "model.json").exists():
        return None
    model, meta, _ = _load_bundle(bundle)
    return model, meta, row["version"]


def current_model_summary() -> dict:
    row = production_row()
    if row is None:
        return {"status": "no_registered_model"}
    return {"status": "ok", **row}


# ── CLI ───────────────────────────────────────────────────────────────────────

def bootstrap() -> None:
    """Register the existing ml/artifacts bundle as the first model and promote
    it to Production (used once, after Plan 02 produced a good model)."""
    if not (cfg.ARTIFACTS_DIR / "model.json").exists():
        raise SystemExit("No ml/artifacts/model.json — train a model first.")
    run_id, version = log_training_run(cfg.ARTIFACTS_DIR, register=True)
    promote(version, cfg.ARTIFACTS_DIR)
    print(f"Bootstrap complete: {version} is Production (run {run_id})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--promote", metavar="VERSION",
                        help="manually promote a registered version (e.g. v3)")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.bootstrap:
        bootstrap()
    elif args.promote:
        src = MODEL_STORE / args.promote
        promote(args.promote, src if (src / "model.json").exists() else None)
    else:
        rows = _registry_rows()
        if not rows:
            print("model_registry is empty — run: python -m ml.registry --bootstrap")
        for r in rows:
            m = r.get("metrics") or {}
            print(f"  {r['version']:>6s}  {r['stage']:<10s}  "
                  f"macro_f1={m.get('macro_f1')}  trained={r.get('trained_at')}")


if __name__ == "__main__":
    main()
