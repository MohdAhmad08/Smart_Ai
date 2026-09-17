# Phase 2 — Plan 03: ML Lifecycle (MySQL + MLflow), Data Retention & Deployment

> **Goal of this document.** A complete, executable plan to turn the one-off model
> from Plan 02 into a **continuously-training, self-monitoring system**: **MySQL**
> holds the (rolling) raw data + events + predictions, a **versioned Parquet feature
> store** is the durable training asset, **MLflow** owns experiment tracking and the
> versioned model registry, an automated pipeline **seals / retrains / evaluates /
> promotes**, **drift** is detected, a **feedback loop** measures live accuracy, and
> the whole stack is **deployed**.
>
> Depends on `PHASE2_01_SYNTHETIC_DATA_GENERATION.md` (data + labels) and
> `PHASE2_02_MODEL_TRAINING_EVALUATION.md` (the `ml/` package + serving).

---

## 0. Lifecycle at a glance

```
   ┌──────────────────────────── MySQL (machine_telemetry) ───────────────────────────────────┐
   │ machine_readings(rolling 14d)  machine_runs  predictions  drift_metrics  feature_snapshots │
   │                                                                          model_registry    │
   └──────┬──────────────┬──────────────────────┬───────────────────────┬──────────────────────┘
          │ seal+extract  │ (labels)             │ (live preds, Plan 02)  │ (dashboard pointer)
          ▼               ▼                       │                        ▲
   Parquet feature store (versioned) ──┐         │                        │
        ┌─────────────────────────────────┐      │                        │
        │  Retraining pipeline (ml/train)  │      │                        │
        │  seal→features→train→eval        │      │                        │
        │  →champion/challenger→promote    │──── log ──────►│             │
        └───────────────┬─────────────────┘     params/metrics/artifacts/dataset            │
                        ▼                                                            │
                ┌───────────────┐    promote to "Production"     ┌──────────────────┴─┐
                │    MLflow      │◄──────────────────────────────│  registry.py glue   │
                │ tracking+reg.  │────── load Production ────────►│ (Plan 02 serving)   │
                └───────┬────────┘                                └─────────────────────┘
                        │ triggers
        ┌───────────────┴───────────────┬─────────────────────────────┐
        ▼                               ▼                             ▼
 APScheduler (nightly)           ml/drift.py (PSI/KS)        feedback loop (preds vs machine_runs)
```

---

# PART A — MySQL tables + the feature store (the lifecycle data model)

| Table / store        | Written by                   | Lifetime        | Role                                                  |
|----------------------|------------------------------|-----------------|------------------------------------------------------|
| `machine_readings`   | consumer / backfill (Plan 01)| **rolling 14 d**| raw extended telemetry (hot tier; sealed then pruned)|
| `machine_runs`       | consumer / backfill (Plan 01)| **forever**     | failure/maintenance events = **label source**        |
| **Parquet feature store** | `ml/retention.py` (seal) | **forever**     | versioned model-ready feature shards (durable asset) |
| `feature_snapshots`  | `ml/retention.py`            | forever         | catalog: version, range, class counts, shard pointer |
| `predictions`        | backend serving (Plan 02)    | forever (small) | every live prediction `{ts, session_id, seq, class, probs, model_version}` |
| `drift_metrics`      | `ml/drift.py`                | forever (small) | periodic PSI/KS per feature + predicted-class-rate shift |
| `model_registry`     | `ml/registry.py`             | forever         | **dashboard pointer**: active version, stage, metrics, trained_at |

Indexes: `predictions(session_id, ts)`, `drift_metrics(ts)`, `model_registry(version)`,
`feature_snapshots(pipeline_version)`. MySQL connection via `DATABASE_URL`
(`backend/app/config.py`). The full retention design is **Part A.2**.

> **Model binaries** live in **MLflow** (with a filesystem/object-store backup —
> GridFS no longer applies on MySQL). `model_registry` holds only metadata + a pointer,
> so the dashboard can show "Production model v7, macro-F1 0.82, trained 2026-06-19" cheaply.

---

# PART A.2 — Data retention & versioned feature store

Second-by-second raw (Plan 01) is rich but bulky, so raw is a **bounded hot tier** and
the **distilled features are the durable asset**. This is what keeps the store from
overflowing while preserving everything needed to retrain forever.

## A.2.1 Four tiers (recap)
- **Hot raw** — `machine_readings`, rolling **14 days**.
- **Labels** — `machine_runs`, **forever** (tiny, irreplaceable).
- **Sealed feature store** — versioned **Parquet** shards, **forever**.
- **Catalog** — `feature_snapshots` (below). `predictions`/`drift_metrics` are small → never pruned.

## A.2.2 The seal-and-prune job — `ml/retention.py`
Scheduled with the retraining APScheduler (Part C). Correct via three watermarks:
- `label_complete_ts = now − H` (H = 24 h): only label rows whose forward horizon is
  complete (newer rows would be censored).
- `max_window` (largest feature window, 6 h): a feature row at `t` needs raw context back
  to `t − max_window`.
- `rolling_keep_ts = now − 14 d`: never prune raw newer than this.

Order is **seal → verify → prune**, idempotent, advancing a `sealed_through_ts`:
1. **Seal** raw in `(sealed_through_ts, rolling_keep_ts]` also older than
   `label_complete_ts`: call `ml.features.seal_range()` (extract at the **1/min stride**
   with trailing context), join labels from `machine_runs`, write a **Parquet shard**
   (partitioned by date/session), insert a `feature_snapshots` row.
2. **Verify** the shard + catalog row are durable.
3. **Prune** raw older than `rolling_keep_ts` whose covering shard is sealed (and not still
   trailing-context for an unsealed row). **Never** prune `machine_runs`.

## A.2.3 `feature_snapshots` table
```sql
CREATE TABLE feature_snapshots (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  pipeline_version VARCHAR(64)  NOT NULL,   -- hash(features.py + config)
  shard_path       VARCHAR(512) NOT NULL,   -- Parquet location
  range_start_ts   DATETIME(3)  NOT NULL,
  range_end_ts     DATETIME(3)  NOT NULL,
  row_count        INT          NOT NULL,
  class_counts     JSON         NOT NULL,   -- {none,bearing,steam_valve,heater,water_pump}
  ref_dist         JSON         NULL,       -- reference feature distribution (for drift, A.2.5)
  created_at       DATETIME(3)  NOT NULL,
  KEY idx_version (pipeline_version),
  KEY idx_range (range_start_ts, range_end_ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## A.2.4 Versioning & reproducibility
`pipeline_version = hash(ml/features.py + ml/config.py)` is stamped on every shard and
model. A training run records its **dataset manifest** (shard list + rolling-window range)
to MLflow → "model vX ⇐ dataset vY ⇐ pipeline vZ". **Caveat (the cost of pruning raw):**
sealed shards are frozen against their pipeline; within the 14-day window features are
recomputable from live raw, but a `features.py` change starts a **new shard lineage** and
old shards age out of relevance as fresh data accumulates.

## A.2.5 Drift reference travels with the snapshot
Because raw is pruned, the drift **reference** distribution (bin edges / summary stats) is
stored in the sealed dataset (`feature_snapshots.ref_dist`) / model artifact — not derived
from raw. Part D compares recent rolling-window features against that stored reference.

---

# PART B — MLflow (tracking + registry)

## B.1 Tracking
Every training run (Plan 02 `train.py`, now wrapped) logs to MLflow:
- **params** — H, window sizes, stride, XGBoost hyperparameters, `pipeline_version`, and
  the **dataset manifest** (sealed shard list + rolling-window range, row counts);
- **metrics** — macro-F1, per-class recall/precision, PR-AUC, lead-time median,
  baseline deltas;
- **artifacts** — the `model.json` bundle (B.8 of Plan 02), confusion matrix PNG,
  SHAP summary, the frozen `FEATURE_COLUMNS`, and the dataset manifest (so the exact
  training set is reproducible — `mlflow.log_input` / a manifest JSON).

```python
import mlflow
mlflow.set_tracking_uri(MLFLOW_URI)          # local file store, or MLflow server
mlflow.set_experiment("machine-pdm")
with mlflow.start_run():
    mlflow.log_params(params); mlflow.log_metrics(metrics)
    mlflow.log_artifact("confusion.png"); mlflow.log_artifact("shap.png")
    mlflow.xgboost.log_model(model, artifact_path="model",
                             registered_model_name="machine-pdm")
```

## B.2 Registry + stages
Registered model `machine-pdm` moves through stages:
`None → Staging → Production → Archived`.

## B.3 Champion / challenger promotion
1. New model is logged and registered → **Staging**.
2. Evaluate the **Staging** candidate on a **fresh holdout** (latest runs).
3. Load current **Production** ("champion"); evaluate on the *same* holdout.
4. **Promote** challenger → Production **only if** it beats champion by a margin on
   the key metric (macro-F1), else archive it.
5. On promotion, archive the old Production and upsert a summary row to the
   `model_registry` table for the dashboard.
6. Start **manual-gated** (require a human OK); flip to fully automatic once trusted
   (the master plan's open follow-up).

The backend (Plan 02 serving) always loads the **Production** model and refreshes
its cache when the registry version changes.

---

# PART C — Retraining pipeline

## C.1 What it does (`ml/train.py`, extended from Plan 02)
```text
seal aged raw → Parquet shards + feature_snapshots (ml/retention.py, Part A.2)
  → assemble dataset: sealed shards (current pipeline_version) ∪ rolling-window features
    (ml/dataset.py, reads MySQL machine_readings ⋈ machine_runs)
  → grouped/time split (ml/dataset.py)
  → train candidate (tuned, early stopping)
  → evaluate on held-out recent runs (ml/evaluate.py)
  → MLflow: log params/metrics/artifacts + dataset manifest, register → Staging
  → champion/challenger (Part B.3) → maybe promote to Production
  → upsert pointer/summary to model_registry
```

## C.2 Triggers (`ml/schedule.py`) — drive **seal + retrain** together
Use **APScheduler** (in-process with the backend, or a standalone worker):
- **Scheduled** — nightly seal + (nightly/weekly) full retrain.
- **Drift-triggered** — Part D flags significant drift → kick a retrain.
- **Volume-triggered** — ≥ K new failure events per class in `machine_runs` since last train.

```python
from apscheduler.schedulers.background import BackgroundScheduler
sched = BackgroundScheduler()
sched.add_job(seal_and_prune, "cron", hour=1)             # nightly seal+prune (Part A.2)
sched.add_job(run_retraining, "cron", hour=2)             # nightly retrain
sched.add_job(check_drift_and_maybe_retrain, "interval", hours=6)
sched.start()
```
(For a simpler FYP deployment, a cron/Windows-Task running `python -m ml.train` is
an acceptable substitute.)

---

# PART D — Drift detection (`ml/drift.py`)

Distribution shift degrades models silently. Periodically compare **recent**
rolling-window feature distributions against the **stored training reference**
(`feature_snapshots.ref_dist` / the model artifact — A.2.5; raw is gone, so the reference
must travel with the snapshot):

- **PSI (Population Stability Index)** per feature:
  `PSI = Σ (recent% − ref%) * ln(recent% / ref%)` over bins.
  Rule of thumb: `<0.1` stable, `0.1–0.25` moderate, `>0.25` significant.
- **KS test** per continuous feature for distribution change.
- **Prediction drift** — shift in predicted class-rate vs training base-rate.

Write results to `drift_metrics` `{ts, feature, psi, ks_p, flag}`. If key features
exceed the PSI threshold → set a flag and trigger retraining (Part C). Optionally
use **Evidently AI** to generate nicer drift reports/dashboards.

---

# PART E — Monitoring / feedback loop (the "self-improving" story)

Closes the loop promised in the proposal:
1. Live predictions accumulate in `predictions` (Plan 02 serving).
2. When a real failure lands in `machine_runs`, **join** it back to the
   predictions that preceded it.
3. Compute rolling **live precision / recall / lead-time** per class.
4. Store these and **surface on the dashboard** (model-health panel) and feed the
   promotion decision (a model that degrades in production gets replaced).

```python
def evaluate_live_outcomes(window_days=7) -> dict:
    # match predictions → subsequent machine_runs failures within H
    # → live per-class recall/precision + lead-time → store + return
```

---

# PART F — Registry glue (`ml/registry.py`)

The single seam between MLflow, the MySQL registry, and the serving backend:
```python
def load_production_model():            # fetch current Production from MLflow (cache)
def current_model_summary() -> dict:    # version, stage, metrics for /api/model/info
def promote_if_better(candidate, holdout, margin): ...   # champion/challenger (B.3)
def mirror_to_registry(summary): ...    # upsert model_registry table row (dashboard pointer)
def backup_to_store(model_bundle): ...  # optional filesystem/object-store binary backup
```
Plan 02's `prediction_service._load_model()` calls `load_production_model()` and
refreshes when the version changes.

---

# PART G — Final deployment

## G.1 Containerize
Dockerfiles already exist for producer/consumer. Add/confirm images for:
- **mysql** — MySQL 8 with a persisted volume (the operational store);
- **backend** — FastAPI + uvicorn (serves API + loads Production model);
- **consumer** — RabbitMQ → MySQL (typed ingest);
- **generator/publisher** — live stream (and an on-demand backfill job);
- **mlflow** — tracking server + registry UI;
- **frontend** — `vite build` static bundle behind **nginx**;
- **scheduler** — APScheduler worker (or fold into backend) for seal/retrain/drift.

## G.2 Compose the stack (top-level `docker-compose.yml`)
Wire: MySQL + RabbitMQ + consumer + generator + backend + mlflow + frontend + scheduler.
Secrets/config via `.env` (already git-ignored). **MySQL runs as a container** with a
persisted volume; the **Parquet feature store** is a mounted volume shared by the
scheduler (seal) and backend/ML (read). Example service sketch:
```yaml
services:
  mysql:      { image: mysql:8, env_file: .env, ports: ["3306:3306"], volumes: ["mysqldata:/var/lib/mysql"] }
  rabbitmq:   { image: rabbitmq:3-management, ports: ["5672:5672","15672:15672"] }
  consumer:   { build: ./rabbitmq/consumer,            env_file: .env, depends_on: [rabbitmq, mysql] }
  generator:  { build: ./rabbitmq/producer/publisher,  env_file: .env, depends_on: [rabbitmq, mysql] }
  mlflow:     { image: ghcr.io/mlflow/mlflow, command: mlflow server ..., ports: ["5000:5000"] }
  backend:    { build: ./backend, env_file: .env, ports: ["8000:8000"], depends_on: [mlflow, mysql],
                volumes: ["featurestore:/app/feature_store"] }
  frontend:   { build: ./frontend, ports: ["80:80"] }   # nginx serving the build
volumes: { mysqldata: {}, featurestore: {} }
```

## G.3 Hosting
- **MySQL + Backend + MLflow** on a small VM or Render; **frontend** as a static build on
  Render / Netlify / Firebase Hosting (per the proposal); point the frontend at the
  deployed API URL via env.
- Persist the **MySQL data volume**, the **Parquet feature store** (volume or cloud
  bucket), and the MLflow backend + artifact store.

## G.4 Ops
- Health checks + restart policies on every service.
- Scheduler container (or backend-embedded APScheduler) drives retraining + drift.
- Document all run commands in the repo `README` (start stack, run backfill, force
  retrain, view MLflow UI).

---

## Step-by-step execution (lifecycle → deployment)
1. Create the MySQL tables + indexes (Part A, incl. `feature_snapshots`); confirm
   `predictions` already fills from Plan 02 serving.
2. Implement `ml/retention.py` + `ml/feature_store.py` (Part A.2); run a seal over the
   backfilled history → Parquet shards + `feature_snapshots` rows; confirm raw older than
   14 d is pruned and `machine_runs` is intact.
3. Add MLflow logging + dataset manifest to `train.py`; run once → see the run + registered
   model in the MLflow UI (Part B.1–B.2).
4. Implement `registry.py` champion/challenger + `mirror_to_registry` (Parts B.3, F);
   point backend serving at `load_production_model()`.
5. Implement `drift.py` (Part D); run recent rolling-window vs stored reference; write
   `drift_metrics`.
6. Implement `schedule.py` triggers (Part C.2): nightly **seal + retrain** + drift check.
7. Implement the feedback loop (Part E); surface live metrics on the dashboard.
8. Containerize + compose (Part G.1–G.2); bring the stack up locally.
9. Deploy to the chosen host (Part G.3); smoke-test end-to-end.

## Verification & acceptance
- **Retention** — after a seal: Parquet shard + `feature_snapshots` row with correct
  per-class counts; raw older than 14 d deleted; `machine_runs` untouched; re-running seal
  is idempotent (no dup shards/double-delete); raw row count plateaus.
- **Reproducibility** — a model's recorded dataset manifest re-assembles to identical rows.
- **Tracking/registry** — MLflow UI shows runs with params/metrics/artifacts and a
  versioned `machine-pdm`; stages transition correctly.
- **Promotion** — a deliberately-better candidate gets promoted to Production and
  the old one archived; `model_registry` pointer + `/api/model/info` update; the
  backend serves the new version without restart.
- **Drift** — artificially shift a feature distribution → `drift_metrics` flags it
  and (if wired) a retrain triggers.
- **Feedback loop** — live precision/recall/lead-time computed from
  `predictions` × `machine_runs` and shown on the dashboard.
- **Deployment** — `docker compose up` brings the full stack online; the deployed
  frontend hits the live API and shows OEE + live predictions end-to-end; MLflow UI
  reachable.

## Pitfalls
- **Seal before prune** — never delete raw that hasn't been sealed + verified into a shard,
  and never delete a row still needed as trailing context (≤ `max_window`) for an unsealed
  feature row. Write the shard + catalog row first, delete raw last.
- **Never prune `machine_runs`** — labels are tiny and irreplaceable; only `machine_readings`
  rolls.
- **Feature-version freeze** — sealed shards are frozen against their `pipeline_version`; a
  `features.py` change starts a new shard lineage. Don't silently mix versions in one dataset.
- **Train/serve consistency** — retraining and serving must share `ml/features.py`
  and the persisted `FEATURE_COLUMNS`/config; version them with the model.
- **Auto-promote too early** — start with a manual gate; a bad auto-promotion can
  silently break live predictions.
- **Drift reference staleness** — refresh the stored reference when a new Production model
  is promoted, else drift fires forever.
- **Holdout leakage in promotion** — champion and challenger must be judged on the
  *same* fresh, never-trained-on holdout (grouped/time split, as in Plan 02 B.5).
- **Secrets** — keep MySQL/RabbitMQ creds in `.env` only (already git-ignored);
  never bake into images.
