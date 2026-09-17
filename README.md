# Manufacturing Intelligence Platform

A full-stack manufacturing analytics and predictive maintenance system built as a Final Year Project. The platform ingests real-time machine telemetry via a message broker, stores it in a relational database, computes OEE (Overall Equipment Effectiveness) KPIs, and runs a trained XGBoost model to predict imminent component failures up to 24 hours in advance.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Data Pipeline](#data-pipeline)
4. [Database Schema](#database-schema)
5. [Machine Learning Pipeline](#machine-learning-pipeline)
6. [Backend API](#backend-api)
7. [Frontend Dashboard](#frontend-dashboard)
8. [Project Structure](#project-structure)
9. [Setup & Running](#setup--running)
10. [API Reference](#api-reference)
11. [ML Model Details](#ml-model-details)
12. [Performance Notes](#performance-notes)

---

## System Overview

The platform monitors industrial paper/textile machines and provides:

- **Real-time OEE tracking** — Availability, Performance, and Quality pillars computed from live sensor readings
- **Predictive maintenance** — XGBoost multi-class classifier that predicts which component (bearing, steam valve, heater, water pump) will fail within the next 24 hours
- **Fleet-level risk ranking** — All machines scored and sorted by failure risk so maintenance teams know where to focus
- **Historical analytics** — Lot production, temperature trends, utility consumption, downtime records
- **Live telemetry streaming** — Machine state, speed, sensor readings delivered via RabbitMQ

---

## Architecture

```
Machine Telemetry
       |
       v
 [RabbitMQ Broker]
       |
       v
 [Consumer Service]  ──>  MySQL (machine_readings, machine_runs)
                                         |
                          ┌──────────────┼──────────────┐
                          v              v              v
                    [FastAPI Backend]  [ML Pipeline]  [Feature Store]
                          |                               (Parquet)
                          v
                   [React Frontend]
```

**Tech stack:**

| Layer | Technology |
|---|---|
| Broker | RabbitMQ |
| Database | MySQL 8 (SQLAlchemy 2.0 + PyMySQL) |
| Backend | FastAPI + Uvicorn |
| ML | XGBoost, pandas, scikit-learn, SHAP |
| Feature Store | Apache Parquet (versioned shards) |
| Frontend | React + TypeScript + Tailwind CSS + Recharts |
| Containerisation | Docker + Docker Compose |

---

## Data Pipeline

### Message Flow

1. **Telemetry source** publishes JSON messages to RabbitMQ at a configurable tick interval (default 30 s).
2. **Consumer** subscribes to the queue and writes typed rows to MySQL — one row per tick in `machine_readings`, one row per failure/repair event in `machine_runs`.
3. **Ingest is idempotent** — `UNIQUE(session_id, seq)` with `INSERT IGNORE` means restarts never produce duplicate rows.

### Message Schema

Each RabbitMQ message is a flat JSON object containing:

```json
{
  "session_id": "uuid",
  "seq": 1234,
  "machine_name": "Machine A",
  "state": "running",
  "ts": "2025-01-15T08:32:10+00:00",
  "plc": {
    "lot_1": 42, "lot_2": 0, "article": "P100",
    "speed": 24.7, "length": 1203.4
  },
  "utility": {
    "sf_flow": 12.3, "wat_flow": 8.1,
    "em_power": 45.2, "em_energy": 1823.4
  },
  "health": {
    "vibration_rms": 0.42, "motor_current": 18.3,
    "bearing_temp": 52.1, "winding_temp": 61.4,
    "air_pressure": 5.8
  },
  "quality": {
    "good_count": 1200, "reject_count": 12
  }
}
```

### Historical Backfill

`rabbitmq/producer/publisher/backfill.py` bootstraps the database with historical data using a parallel multi-process strategy — one process per machine, overlapping DB writes with computation via a writer thread.

```bash
# Run from rabbitmq/producer/publisher/
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
  GEN_DT_SECONDS=30 GEN_SIM_WEEKS=53 GEN_ACCEL=0.4 \
  GEN_NO_CALENDAR=1 GEN_BATCH_SIZE=1000 \
  python backfill.py
```

---

## Database Schema

MySQL database `machine_telemetry`. All DDL is managed by SQLAlchemy (`backend/app/models.py`).

### `machine_readings`

Primary telemetry store — one row per tick.

| Column | Type | Description |
|---|---|---|
| `id` | BIGINT PK | Auto-increment |
| `session_id` | VARCHAR(36) | UUID linking readings to a run session |
| `seq` | INT | Monotone tick counter within session |
| `machine_name` | VARCHAR(64) | Physical machine identifier |
| `state` | VARCHAR(16) | `running` / `idle` / `maintenance` / `error` / `changeover` |
| `ts` | DATETIME(3) | Tick timestamp (UTC) |
| `speed` | FLOAT | Production speed (m/min) |
| `vibration_rms` | FLOAT | RMS vibration amplitude |
| `bearing_temp` | FLOAT | Bearing temperature (°C) |
| `winding_temp` | FLOAT | Motor winding temperature (°C) |
| `motor_current` | FLOAT | Motor current draw (A) |
| `em_power` | FLOAT | Electrical power (kW) |
| `sf_flow` | FLOAT | Steam flow rate |
| `wat_flow` | FLOAT | Water flow rate |
| `air_pressure` | FLOAT | Air supply pressure (bar) |
| `good_count` | INT | Cumulative good-product count |
| `reject_count` | INT | Cumulative rejected-product count |

**Indexes:** `idx_reading_ts (ts)`, `idx_reading_machine (machine_name)`, `UNIQUE(session_id, seq)`

**Covering index for OEE queries:**
```sql
CREATE INDEX idx_oee_cover
ON machine_readings (ts, machine_name, state, speed, good_count, reject_count);
```

### `machine_runs`

Failure/repair event log — one row per failure event. Never pruned.

| Column | Type | Description |
|---|---|---|
| `session_id` | VARCHAR(36) | Links to readings in the same session |
| `machine_name` | VARCHAR(64) | Machine identifier |
| `component` | VARCHAR(32) | Failed component: `bearing`, `steam_valve`, `heater`, `water_pump` |
| `severity` | VARCHAR(16) | Failure severity |
| `run_start_ts` | DATETIME | Start of the production run |
| `failure_ts` | DATETIME | Timestamp of failure event |
| `repair_ts` | DATETIME | Timestamp repair completed |
| `run_hours_to_failure` | FLOAT | Hours from run start to failure |

### `feature_snapshots`

Catalog of sealed Parquet feature shards for versioned ML training datasets.

### `generator_state`

Checkpoint table — one row per machine, used for resumable data generation.

### `predictions`

Audit log of all model predictions made by the serving layer.

---

## Machine Learning Pipeline

### Overview

A 5-class XGBoost classifier predicts which component will fail within the next **24 hours**, or none if the machine is healthy. Classes: `none`, `bearing`, `steam_valve`, `heater`, `water_pump`.

### Feature Engineering (`ml/features.py`)

Features are computed from a **rolling window** of the most recent sensor readings. Three window sizes are used (20, 60, and 180 readings — corresponding to 10 min, 30 min, and 90 min at a 30 s tick rate).

For each of 9 sensor signals × 3 windows × 3 statistics = **81 rolling features**:
- `_w{N}_mean` — rolling mean
- `_w{N}_std` — rolling standard deviation
- `_w{N}_slope` — linear slope over the window

Plus **11 derived features**:
- Cross-sensor ratios: `current_per_speed`, `power_per_speed`, `vib_per_current`, `sf_per_speed`, `wat_per_speed`
- Totalizer rates: `sf_tot_rate`, `wat_tot_rate`, `em_energy_rate`
- `reject_pct` — reject fraction over the last window
- `is_running` — binary state flag
- `machine_time_h` — cumulative machine age in hours

Total: **92 features** per sample.

### Label Generation (`ml/labels.py`)

Each feature row is labelled by looking **24 hours ahead**:
- If a failure of component X occurs within the next 24 hours → label = X
- Otherwise → label = `none`

Only failure events where component health fell below a threshold (88%) are labelled; healthy maintenance events are excluded.

### Training (`ml/train.py`)

```bash
python -m ml.train            # train (or resume from checkpoint)
python -m ml.train --reset    # fresh start
python -m ml.train --tune     # Optuna hyperparameter search first
```

**Dataset split strategy:**
- Time-based split: first 75% of timeline → train, next 12.5% → validation, 24 h gap between splits
- Stratified test set: 15% of each failure class drawn independently from any point in time (ensures test set has failure examples)
- Majority-class subsampling: `none` class capped at 2× the total failure count to address class imbalance

**Checkpoint / resume:** Every 25 boosting rounds a checkpoint is saved to `ml/artifacts/checkpoint.json`. If training crashes (OOM or otherwise), the next run resumes from the last checkpoint automatically with no data loss.

**Model hyperparameters:**

```python
n_estimators=400, max_depth=6, learning_rate=0.05,
subsample=0.7, colsample_bytree=0.7,
min_child_weight=5, gamma=0.1, reg_lambda=1.0,
tree_method="hist", max_bin=200
```

### Evaluation (`ml/evaluate.py`)

- **Macro-F1: 0.71** at the cost-aware operating point (0.64 argmax, 0.13 "always none" baseline)
- **Per-class recall:** bearing 0.84, water_pump 0.82, steam_valve 0.80, heater 0.78
- **PR-AUC:** bearing 0.82, water_pump 0.80, none 0.88
- **Median lead time:** ~11 hours before failure (all classes)
- SHAP feature importance plots saved to `ml/artifacts/plots/`

**Cost-aware decision thresholds.** A missed failure costs far more than a false
alarm, so per-class probability thresholds are tuned on the validation set by
maximising F2 (recall weighted 4× precision). A failure class fires when its
probability clears its threshold; ties go to the class furthest above. The
thresholds are persisted in `metadata.json` (`decision_thresholds`) and the
identical rule (`ml.evaluate.apply_thresholds`) runs in evaluation AND live
serving — no train/serve skew.

### Feature Store & Retention (`ml/feature_store.py`, `ml/retention.py`)

Raw `machine_readings` are kept for a **rolling 14-day window**. The `seal_range()` function extracts features + labels from a time slice, writes them to a versioned **Parquet shard** (`ml/feature_store/<pipeline_version>/dt=YYYY-MM-DD/part-*.parquet`), and records the shard in the `feature_snapshots` catalog. `prune_old_readings()` then deletes raw rows older than the rolling window. `machine_runs` (failure events) are **never pruned**.

**Pipeline versioning:** The pipeline version (`v1.<hash>`) is a SHA-256 hash of all constants that affect feature or label computation. Changing a sensor column or window size auto-invalidates the cached feature store.

### Live Serving (`backend/app/services/prediction_service.py`)

The same `ml/features.py` code path used in training is imported directly into the serving layer — no feature skew possible. For each prediction request:
1. Fetch the last 200 readings for the machine from MySQL
2. Run `build_features_for_machine()` to produce the feature vector
3. Score with the cached XGBoost model, apply the cost-aware thresholds
4. Return `predicted_class`, per-class probabilities, and `risk_score = 1 - P(none)`
5. Log the prediction to the `predictions` audit table (sim-time `ts` of the scored reading, so the feedback loop can join it against failures)

The backend loads whichever model version the **registry points at Production**
(`model_registry` table → `ml/model_store/<version>/` bundle) and hot-reloads
within 30 s of a promotion — zero-downtime model updates. With no registry row
it falls back to `ml/artifacts/`.

---

## ML Lifecycle (Phase 2 Plan 03)

The one-off model is wrapped in a continuously-training, self-monitoring system:

```
 machine_readings (rolling 14 d)         machine_runs (labels, forever)
        │  seal → verify → prune                │
        ▼                                       │
 Parquet feature store  ──────────────┐         │
 (ml/feature_store/<pv>/<machine>/)   ▼         ▼
                          retraining pipeline (python -m ml.train)
                          shards ∪ rolling raw → train → evaluate
                                   │
                     MLflow (runs, params, metrics, artifacts,
                     dataset manifest, registered model machine-pdm)
                                   │ champion/challenger (macro-F1 + margin)
                                   ▼
                    Production alias + model_registry row + model_store bundle
                                   │
        ┌──────────────────────────┼─────────────────────────┐
        ▼                          ▼                         ▼
  backend serving           ml/drift.py (PSI/KS)      ml/feedback.py
  (loads Production)        → drift_metrics           predictions × machine_runs
                            → triggers retrain        → live_metrics → dashboard
```

### Retention — `ml/retention.py`

Nightly **seal → verify → prune** keeps `machine_readings` a bounded rolling
14-day window (anchored to MAX(ts), so it works on backfilled sim data too):

- **Seal**: per machine, walk from the sealed watermark (from the
  `feature_snapshots` catalog) to `now − 14 d` in 30-day chunks; each chunk
  becomes one Parquet shard of feature rows + labels at the training stride.
- **Verify**: every shard is read back and its row/class counts checked before
  the catalog row is written — pruning trusts only catalogued shards.
- **Prune**: batched `DELETE` (50 k rows/txn) of raw strictly older than every
  machine's sealed watermark minus a 6 h context margin. `machine_runs` is
  never touched.

```bash
python -m ml.retention --dry-run     # what would happen
python -m ml.retention --no-prune    # seal + verify only
python -m ml.retention               # the real nightly job
```

### Dataset assembly — `ml/dataset.py`

Training data is the union of **sealed shards ∪ features freshly extracted
from the rolling raw window** (after each machine's sealed watermark). Verified
to reproduce the pre-lifecycle dataset to within a few boundary rows
(2,670,750 vs 2,670,755 rows, identical class distribution). Every training run
receives a **dataset manifest** (shard list + fresh ranges) that is logged to
MLflow for reproducibility.

### Registry — `ml/registry.py`

- MLflow tracking + model registry (`machine-pdm`), aliases `staging`/`production`
- Champion/challenger promotion (Part B.3): challenger and current champion are
  evaluated on the **same fresh holdout**; promote only if the challenger wins
  by `PROMOTE_MARGIN` (default 0.005). `PROMOTE_MODE=manual` turns on a manual
  gate (`python -m ml.registry --promote vN`).
- Every registered version is mirrored to the `model_registry` MySQL table
  (the cheap dashboard pointer) and backed up to `ml/model_store/<version>/`
  (what serving actually loads — no MLflow dependency at serve time).

```bash
python -m ml.registry --bootstrap    # register the existing ml/artifacts bundle as v1 Production
python -m ml.registry --status       # list versions/stages
python -m ml.registry --promote v3   # manual promotion
mlflow ui --backend-store-uri sqlite:///ml/mlflow.db   # experiment browser
```

### Retraining — `python -m ml.train`

The Plan 02 trainer now: assembles from the feature store, trains with
checkpoint/resume, tunes cost-aware thresholds on val, evaluates, stamps the
drift reference (`ref_dist`, train-set feature histograms) into the bundle,
logs everything to MLflow, registers → Staging, and runs champion/challenger.
`--smoke` runs the whole pipeline in ~5 min on thinned data (artifacts to a
scratch dir, never promoted) to verify the plumbing.

### Drift — `ml/drift.py`

Every 6 h, PSI + KS per feature comparing the last 3 days of features against
the Production model's stored `ref_dist` (monotone counters like
`machine_time_h` are excluded — they always drift by design), plus
predicted-class-rate drift from the `predictions` table. Results land in
`drift_metrics`; ≥ 5 significant features (PSI > 0.25) recommends a retrain,
which the scheduler triggers (12 h cooldown).

### Feedback loop — `ml/feedback.py`

Joins `predictions` back to the `machine_runs` failures that followed:
per-class **live recall** (failures with a correct warning in the prior 24 h),
**live precision** (horizon-complete predictions that came true), and **lead
time**. Written to `live_metrics` hourly and surfaced on the dashboard
model-health panel.

### Scheduler — `python -m ml.schedule`

APScheduler worker: seal+prune nightly 01:00, retrain 02:00, drift + volume
trigger (≥ 3 new failures since last train) every 6 h, feedback hourly.
`--once seal|retrain|drift|feedback|volume` runs any job immediately (cron-friendly).

---

## Backend API

FastAPI application in `backend/app/`. Run with:

```bash
# From backend/
PYTHONUTF8=1 python -m uvicorn app.main:app --port 8077 --reload
```

### OEE Endpoints

**`GET /api/oee`**

Returns one OEE summary row per machine over the most recent 7-day window.

```json
[
  {
    "machine_id": "Machine A",
    "machine_name": "Machine A",
    "availability": 96.1,
    "performance": 87.4,
    "quality": 80.2,
    "oee": 67.3
  }
]
```

**OEE formula:**
- Availability = running\_time / (running + error + maintenance)
- Performance = mean(speed | running) / NOMINAL\_SPEED, clamped to 1.0
- Quality = good\_count / (good\_count + reject\_count)
- OEE = A × P × Q

**`GET /api/oee/timeseries?machine=&range=`**

Bucketed OEE for trend charts. `range` ∈ `{day, week, month, year}` — each selects both bucket granularity and lookback window. All windows are anchored to `MAX(ts)` in the database, not wall clock time (works correctly on historical data).

| Range | Bucket | Window |
|---|---|---|
| `day` | Hourly | Last 24 h |
| `week` | Hourly | Last 7 days |
| `month` | Daily | Last 30 days |
| `year` | Daily | Last 365 days |

### Prediction Endpoints

**`GET /api/predict/{machine}`**

Score a single machine. Returns predicted component, per-class probabilities, and risk score.

```json
{
  "machine_name": "Machine A",
  "predicted_class": "bearing",
  "probabilities": {
    "none": 0.312,
    "bearing": 0.521,
    "steam_valve": 0.089,
    "heater": 0.041,
    "water_pump": 0.037
  },
  "risk_score": 0.688,
  "model_version": "v1.b2cd401f22",
  "ts": "2025-01-15T09:00:00+00:00"
}
```

**`GET /api/maintenance`**

Score all machines in the fleet, sorted by `risk_score` descending. Use this as the maintenance priority queue.

**`GET /api/model/info`**

Returns loaded model metadata: registry version, pipeline version, feature count, class names, decision thresholds, prediction horizon.

**`GET /api/model/health`**

Model-health panel payload: Production registry row (version, stage, metrics), recent version history, latest live feedback metrics per class, and drift status.

**`GET /api/model/registry`**

Model version history from the `model_registry` table (newest first).

### Analytics Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/analytics/lot` | Lot-level production summary |
| `GET /api/analytics/temperature` | Temperature trend data |
| `GET /api/analytics/production` | Production rate analytics |
| `GET /api/analytics/utilities` | Steam, water, power consumption |
| `GET /api/machines` | Machine list and current states |
| `GET /api/alerts` | Active alert history |
| `GET /api/records` | Downtime and event records |
| `GET /api/utilities` | Utility meter readings |

---

## Frontend Dashboard

React + TypeScript SPA in `frontend/`. Built with Vite, Tailwind CSS, and Recharts.

**Views:**
- **Dashboard** — KPI cards (OEE pillars), machine status indicators, live speed gauges
- **Production Floor** — Floor-level view of all machines with state indicators
- **OEE Analytics** — OEE trend charts per machine (day/week/month/year toggle)
- **Enhanced Analytics** — Lot analytics, temperature trends, utility consumption charts
- **Maintenance Schedule** — Fleet risk ranking from `/api/maintenance`, colour-coded by risk score
- **Alert History** — Timestamped alert log
- **Database View** — Raw record browser with pagination

```bash
# From frontend/
npm install
npm run dev
```

---

## Project Structure

```
Taha_fyp/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, router registration
│   │   ├── config.py            # DATABASE_URL, sys.path setup
│   │   ├── database.py          # SQLAlchemy engine, session, helpers
│   │   ├── models.py            # ORM: Reading, MachineRun, FeatureSnapshot, ...
│   │   ├── routes/
│   │   │   ├── oee.py           # /api/oee, /api/oee/timeseries
│   │   │   ├── prediction.py    # /api/predict/{machine}, /api/maintenance
│   │   │   ├── analytics.py     # /api/analytics/*
│   │   │   ├── machine.py       # /api/machines
│   │   │   ├── alerts.py        # /api/alerts
│   │   │   ├── records.py       # /api/records
│   │   │   └── utilities.py     # /api/utilities
│   │   └── services/
│   │       ├── oee_service.py         # OEE pillar computation (SQL GROUP BY)
│   │       ├── prediction_service.py  # Model loading + live scoring
│   │       ├── analytics_service.py
│   │       ├── machine_service.py
│   │       ├── alerts_service.py
│   │       ├── records_service.py
│   │       └── utilities_service.py
│   └── run.py
│
├── ml/
│   ├── config.py          # All tunable constants, pipeline version hash
│   ├── db.py              # ML-side DB reader (pandas DataFrames)
│   ├── tables.py          # Lifecycle table DDL (ml-side, idempotent)
│   ├── features.py        # Feature engineering (shared training + serving)
│   ├── labels.py          # 24 h lookahead label generation
│   ├── dataset.py         # Assembly from shards ∪ rolling raw + splits
│   ├── train.py           # XGBoost training + MLflow log/register/promote
│   ├── evaluate.py        # Metrics, cost-aware thresholds, SHAP, lead-time
│   ├── feature_store.py   # Parquet shard write/verify/read + catalog + ref_dist
│   ├── retention.py       # Seal → verify → prune (rolling 14-day raw window)
│   ├── registry.py        # MLflow registry glue + champion/challenger + mirror
│   ├── drift.py           # PSI/KS feature drift + prediction drift
│   ├── feedback.py        # Live outcomes: predictions × machine_runs
│   ├── schedule.py        # APScheduler worker (seal/retrain/drift/feedback)
│   ├── Dockerfile         # Scheduler/trainer container image
│   ├── model_store/       # Versioned serving bundles (v1/, v2/, ...)
│   ├── feature_store/     # Sealed Parquet shards (<pipeline_version>/<machine>/)
│   ├── mlflow.db          # Local MLflow backend (sqlite; use server in Docker)
│   └── artifacts/
│       ├── model.json          # Latest trained XGBoost model
│       ├── metadata.json       # Pipeline version, features, thresholds, ref_dist
│       └── plots/             # SHAP and confusion-matrix plots
│
├── rabbitmq/
│   ├── producer/
│   │   ├── publisher/
│   │   │   ├── machine_data_generator.py  # Stochastic degradation engine
│   │   │   ├── backfill.py                # Parallel historical bootstrap
│   │   │   └── publisher.py              # Live RabbitMQ publisher
│   │   └── setup/                         # Broker provisioning
│   └── consumer/
│       └── Dockerfile                     # Consumer container
│
└── frontend/
    ├── src/
    │   ├── components/        # React UI components
    │   └── ...
    └── index.html
```

---

## Setup & Running

### Prerequisites

- Python 3.10+
- Node.js 18+
- MySQL 8
- RabbitMQ (or Docker)

### 1. Database

```sql
CREATE DATABASE machine_telemetry CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Tables are created automatically by FastAPI on startup (`create_tables()`).

Add the OEE covering index after tables are created:

```sql
CREATE INDEX idx_oee_cover
ON machine_readings (ts, machine_name, state, speed, good_count, reject_count);
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
# Set DATABASE_URL in environment or .env
PYTHONUTF8=1 python -m uvicorn app.main:app --port 8077 --reload
```

### 3. ML Training

```bash
cd ml
pip install -r requirements.txt    # xgboost, pandas, scikit-learn, shap, optuna
python -m ml.train                 # trains from data in MySQL
# Artifacts saved to ml/artifacts/model.json + metadata.json
```

### 4. RabbitMQ Consumer

```bash
cd rabbitmq/consumer
docker compose up -d
```

### 5. Frontend

```bash
cd frontend
npm install
npm run dev    # dev server on :5173
```

### 6. ML lifecycle (after the first model is trained)

```bash
python -m ml.registry --bootstrap   # once: register current model as v1 Production
python -m ml.retention              # seal aged raw into Parquet shards, prune
python -m ml.schedule               # start the lifecycle worker (blocking)
# or run individual jobs: python -m ml.schedule --once drift|feedback|retrain
```

### 7. Full stack with Docker (deployment)

```bash
cp .env.example .env                # edit credentials
docker compose up -d --build
# frontend  -> http://localhost         (nginx, /api proxied to backend)
# backend   -> http://localhost:8000
# mlflow UI -> http://localhost:5000
# rabbitmq  -> http://localhost:15672
```

Services: `mysql`, `rabbitmq`, `consumer`, `generator` (live telemetry),
`backend`, `mlflow` (tracking server + registry UI), `scheduler` (lifecycle
worker), `frontend`. The Parquet feature store and model bundles live on shared
volumes; MySQL data persists in `mysqldata`.

---

## API Reference

### OEE

```
GET /api/oee                          -> OEE snapshot (last 7 days, all machines)
GET /api/oee/timeseries               -> Hourly OEE, last 7 days, all machines
GET /api/oee/timeseries?machine=X     -> Filter to one machine
GET /api/oee/timeseries?range=month   -> Daily OEE, last 30 days
GET /api/oee/timeseries?range=year    -> Daily OEE, last 365 days
```

### Predictions & Maintenance

```
GET /api/predict/{machine}            -> Score one machine
GET /api/maintenance                  -> Score all machines, sorted by risk
GET /api/model/info                   -> Loaded model metadata
```

### Analytics

```
GET /api/analytics/lot                -> Lot production summary
GET /api/analytics/temperature        -> Temperature trends
GET /api/analytics/production         -> Production rate data
GET /api/analytics/utilities          -> Utility consumption
GET /api/machines                     -> Machine list + states
GET /api/alerts                       -> Alert history
GET /api/records                      -> Downtime records
GET /api/utilities                    -> Utility meters
```

---

## ML Model Details

### Sensors Used as Model Input

| Sensor | Failure signature |
|---|---|
| `vibration_rms` | Bearing degradation (rises before failure) |
| `bearing_temp` | Bearing degradation (thermal runaway) |
| `winding_temp` | Heater / motor insulation degradation |
| `sf_flow` | Steam valve leak or blockage (flow drift) |
| `wat_flow` | Water pump wear (flow drop) |
| `motor_current` | General mechanical load stress |
| `em_power` | Electrical stress |
| `air_pressure` | Air supply health |
| `speed` | Production rate context |

### SHAP Top Features (by mean absolute impact)

The model's top predictors are physically sensible:
- `reject_pct` (quality degradation = leading indicator of all failures)
- `vibration_rms_w180_std` (bearing signature — long-window volatility)
- `air_pressure_w60_mean` (air system health)
- `winding_temp_w60_slope` (heater signature — temperature trend)
- `bearing_temp_w180_mean` (bearing thermal baseline)
- `wat_per_speed` (water pump output normalised to speed)

### Training Data Statistics

The model was trained on one year of telemetry from 5 machines:
- **5,342,400** total readings (30 s ticks, 365 days)
- **516** failure events across 4 component types
- Class distribution after subsampling: none 75%, bearing 11%, water_pump 7%, steam_valve 5%, heater 2%
- Median run-to-failure: 13–14 sessions per machine over the year

---

## Performance Notes

| Query | Latency |
|---|---|
| `/api/oee` snapshot (7 days) | ~400 ms |
| `/api/oee/timeseries` week (hourly) | ~170 ms |
| `/api/oee/timeseries` month (daily) | ~2.4 s |
| `/api/predict/{machine}` | ~2 s |
| `session_name_map()` | ~60 ms (was 32 s before covering index) |

The `year` timeseries over all machines is the heaviest query (~65 s) because `DATE_FORMAT` daily bucketing over 5M+ rows cannot use the index for grouping. This path is acceptable in practice — filter to a single machine to reduce to ~13 s.
