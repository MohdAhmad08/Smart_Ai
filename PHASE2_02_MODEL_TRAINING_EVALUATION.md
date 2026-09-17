# Phase 2 — Plan 02: OEE Analytics, XGBoost Model & Live Serving

> **Goal of this document.** A complete, executable plan to (A) compute and plot
> **OEE** from the generated data, (B) build, train, and rigorously evaluate the
> **XGBoost multi-class** maintenance predictor, and (C) **serve the model so live
> machine runs show predicted results on the dashboard — the main use case.**
>
> Depends on `PHASE2_01_SYNTHETIC_DATA_GENERATION.md` (the data + labels).
> Feeds `PHASE2_03_ML_LIFECYCLE.md` (registry, retraining, deployment).

---

## 0. Where this sits

```
[Plan 01] generator → machine_readings + machine_runs (labels)
                          │
        ┌─────────────────┼──────────────────────────┐
        ▼                 ▼                            ▼
   PART A: OEE      PART B: XGBoost model        (Plan 03: lifecycle)
   (analytics)      (train + evaluate)
        │                 │
        └──────► PART C: serve to dashboard (OEE graph + live predictions)
```

OEE (Part A) needs only Plan 01's data — no ML — so it can be built first and in
parallel. The model (Part B) and its live display (Part C) are the headline.

---

## 0.1 Data access — MySQL via SQLAlchemy (shared by backend + ML)

Plan 01 moved the store to **MySQL**. Before Parts A–C, rewrite the access layer:

- **`backend/app/models.py`** (new, shared) — SQLAlchemy ORM `Reading` + `MachineRun`
  (the tables in Plan 01 §11/§12). Imported by the consumer, the backend, and `ml/`.
- **`backend/app/database.py`** — replace the PyMongo client with a SQLAlchemy engine +
  `SessionLocal`; **keep the helper names** (`to_float`, `hms_to_minutes`,
  `parse_timestamp`, `map_status`) so services barely change. They now run mostly at
  **ingest** (consumer), since columns are already typed; `session_name_map()` becomes one
  grouped query:
  ```python
  def session_name_map(db) -> dict[str, str]:
      rows = db.execute(select(Reading.session_id, func.min(Reading.ts).label("first_ts"))
                        .group_by(Reading.session_id).order_by("first_ts")).all()
      return {sid: f"Machine {i+1}" for i, (sid, _) in enumerate(rows)}
  ```
- **Convert the 5 services** (`analytics_service`, `records_service`, `utilities_service`,
  `alerts_service`, `machine_service`) from `readings_collection()` / aggregation to
  `select(...)`. Representative mappings:

  | Mongo today | MySQL (SQLAlchemy) |
  |---|---|
  | `col.distinct("session_id")` | `select(Reading.session_id).distinct()` |
  | `col.find_one({"session_id": sid}, sort=[("seq",1)])` | `select(Reading).where(Reading.session_id==sid).order_by(Reading.seq).limit(1)` |
  | latest window for a machine | `select(Reading).where(...).order_by(Reading.seq.desc()).limit(W)` |
  | OEE state-duration counts | `select(Reading.state, func.count()).group_by(Reading.state)` |

- **Config** — `backend/app/config.py` exposes `DATABASE_URL`
  (`mysql+pymysql://…/machine_telemetry?charset=utf8mb4`). Deps: `SQLAlchemy>=2.0`,
  `PyMySQL>=1.1`, `cryptography`.

---

# PART A — OEE (Overall Equipment Effectiveness)

## A.1 Formulas

**OEE = Availability × Performance × Quality** (each ∈ [0, 1]; report as %).

| Pillar           | Definition                                             | Source fields (from Plan 01)                         |
|------------------|--------------------------------------------------------|------------------------------------------------------|
| **Availability** | Run Time / Planned Production Time                      | `state` durations                                    |
| **Performance**  | actual throughput / ideal throughput                   | `plc.speed` vs `nominal_speed` (or `length` produced)|
| **Quality**      | good / (good + reject)                                  | `quality.good_count`, `quality.reject_count`         |

Precisely, per machine over a time bucket:
```text
planned_production_time = total_time − planned_stops        # planned_stops = idle/changeover (breaks)
run_time                = planned_production_time − unplanned_downtime   # unplanned = error + breakdown maintenance
Availability = run_time / planned_production_time
Performance  = mean(speed during run) / nominal_speed       # clamp to [0,1]
Quality      = Σ good_count / (Σ good_count + Σ reject_count)
OEE          = Availability * Performance * Quality
```
World-class OEE ≈ 85%; our degrading machines should sag below that and dip around
downtime — exactly what makes the graph interesting.

## A.2 Backend — `backend/app/services/oee_service.py`

Use the SQLAlchemy access layer (§0.1): a `Session`, the `Reading` ORM model, and the
retained helpers (`map_status`, `session_name_map`). Pillars come from SQL — e.g. state
durations via `select(Reading.state, func.count()).group_by(Reading.state)`, throughput
from `speed`/`length` columns, quality from `good_count`/`reject_count` sums.

```python
def get_oee_snapshot() -> list[dict]:
    # per machine (session): A, P, Q, OEE over its whole run.
    # Upgrades the existing get_oee_list() so pillars come from REAL
    # state/throughput/quality instead of constants (quality no longer hardcoded 100).

def get_oee_timeseries(machine: str | None, range: str = "shift") -> list[dict]:
    # bucket each machine's readings by hour | shift | day
    # for each bucket compute A, P, Q, OEE (A.1)
    # return [{ machine, time, availability, performance, quality, oee }]
```

Implementation notes:
- Derive per-bucket state durations by counting consecutive readings in each
  `state` × `dt` (or by timestamp deltas).
- Guard empty buckets: if `planned_production_time == 0`, emit `null`/skip — never
  divide by zero (this caused the earlier `toFixed`/undefined crash).
- `range`: `shift` (default) | `day` | `week` controls bucket size + window.

## A.3 Routes — `backend/app/routes/` (analytics or new `oee.py`)
```python
@router.get("/oee")                 # snapshot (already exists → upgrade)
def oee():            return get_oee_snapshot()

@router.get("/oee/timeseries")      # NEW — for the trend graph
def oee_timeseries(machine: str | None = Query(None), range: str = Query("shift")):
    return get_oee_timeseries(machine, range)
```
Register in `backend/app/main.py` if a new `oee.py` router is added.

## A.4 Frontend — extend the existing OEEChart
- Add an **OEE trend line over time** (x = bucket time, y = OEE %), with optional
  Availability / Performance / Quality sub-lines.
- Add a **per-machine selector** and a **range toggle** (shift / day / week)
  hitting `/api/oee/timeseries`.
- Defensive rendering: default missing/`null` buckets, guard `toFixed` on possibly
  undefined values (the bug class hit earlier).

## A.5 OEE verification
- `/api/oee` returns each pillar `< 100%` and **Quality ≠ constant 100**.
- `/api/oee/timeseries?machine=Machine%201&range=shift` returns ordered buckets;
  OEE visibly **dips around `error`/downtime** windows.
- Trend graph renders for every machine with no console errors.

---

# PART B — XGBoost multi-class maintenance model

## B.1 Problem framing
`xgboost.XGBClassifier(objective="multi:softprob", num_class=5)` predicting the
**next-imminent failure within horizon H** (start **H = 24 sim-hours**):

```
classes = {none, bearing, steam_valve, heater, water_pump}
```
Secondary view: collapse to binary "any failure soon" for an extra metric.
RUL regression is an optional stretch, not required.

## B.2 The `ml/` package
```
ml/
  config.py        # H, window sizes, feature stride, feature list, paths, class names
  features.py      # SHARED feature engineering (train AND serve); batch-seal mode; pipeline_version
  labels.py        # join readings ↔ machine_runs → multi-class label
  feature_store.py # Parquet shard read/write + feature_snapshots catalog helpers
  dataset.py       # assemble leakage-safe train/val/test from (sealed shards ∪ rolling raw)
  retention.py     # seal-and-prune job (Plan 03 owns the schedule)
  train.py         # train + tune + (Plan 03: MLflow log + register + dataset manifest)
  evaluate.py      # metrics, confusion, lead-time, baselines, SHAP
```

`features.py` exposes a **`pipeline_version = hash(features.py source + cfg)`** that is
stamped onto every sealed Parquet shard and every model artifact (so a model's exact
feature definition is always reproducible). `config.py` carries a **feature stride**
(default **1/min**): even though raw is per-second, sealed feature rows are emitted once
per minute — the rolling-window stats already summarise the intervening seconds.

## B.3 Feature engineering — `ml/features.py` (the real work)
Instantaneous sensor values are weak; **trends and variability over time** carry
the predictive signal. This module is imported by **both** training and live
inference so features are computed identically (no train/serve skew).

Input: an ordered (by `seq`) window of one machine's readings. Output: one feature
row. Compute over rolling windows `W ∈ {10, 30, 60 readings, 1h, 6h}`:

| Feature family            | Examples                                                        | Why it matters                       |
|---------------------------|----------------------------------------------------------------|--------------------------------------|
| Rolling stats             | mean/std/min/max/last of vibration, currents, temps, flows     | level + variability                  |
| **Slope (linear fit)**    | slope of `vibration_rms`, `bearing_temp`, `winding_temp` over W | **rising trend = impending failure** |
| Deltas / rate-of-change   | value − value N steps ago                                      | short-term acceleration              |
| Deviation from setpoint   | `SF_Flow − sf_setpoint`, flow per unit speed                   | valve/pump drift                     |
| Totalizer rates           | `SF_Tot`/`Wat_Tot`/`EM_Energy` Δ per minute                    | efficiency loss                      |
| Cumulative-since-repair   | run-hours (`machine_time` Δ), cumulative lots/energy           | wear proxy                           |
| Cross-sensor ratios       | current/speed, power/length, temp − ambient                    | load-normalized stress               |

Explicitly **drop** `_truth.*`, raw ids, and timestamps from the feature matrix
(keep `session_id` only as a CV group key, not a feature).

```python
def build_feature_row(window: list[dict], cfg) -> dict: ...      # one row from a trailing raw window
def build_feature_frame(readings_by_session: dict, cfg) -> pandas.DataFrame: ...
def seal_range(start_ts, end_ts, cfg) -> pandas.DataFrame: ...   # batch-seal: extract @ stride over a time range
FEATURE_COLUMNS: list[str]   # frozen order, persisted with the model artifact
pipeline_version: str        # hash(features.py + cfg) — stamped on shards + models
```

`seal_range` is the **batch-seal** entry point used by `ml/retention.py` (Plan 03): it
pulls the raw rows for `[start_ts, end_ts]` (plus the trailing `max_window` of context),
emits feature rows at the configured **stride**, and returns the frame that gets written
to a Parquet shard. The same `build_feature_row` is used live at serving time — one code
path, no train/serve skew.

## B.4 Labelling — `ml/labels.py`
For a reading at time `t` on machine `m`, find the **next** `machine_runs` failure
event for `m` after `t`:
```text
label(t) = component   if (failure_ts − t) ≤ H
           "none"       otherwise
```
Yields the 5 classes; `none` will dominate (expected — handled in B.6).

## B.5 Dataset assembly + leakage-safe splitting — `ml/dataset.py`
**This is the most error-prone step; getting it wrong silently inflates scores.**
- Assemble X/y from **two unioned sources**: (a) **sealed Parquet shards** of the current
  `pipeline_version` (the aged, frozen history, read via `ml/feature_store.py`), and
  (b) **features freshly extracted from the rolling 14-day raw window** via a SQL read of
  `machine_readings` (using `build_feature_frame`). Labels (B.4) come from `machine_runs`
  (kept forever) — a clean SQL/pandas merge on `session_id` + `failure_ts ≥ ts`. Drop
  `truth_json` and ids before assembling `FEATURE_COLUMNS`.
- **Never random-split** — consecutive readings are near-identical, so a random
  split leaks the future into the test set and produces fake ~100% accuracy.
- Split **by machine-run / time**:
  - Hold out **whole sessions** (machine instances) for test, or
  - Split by time: train on earlier runs, test on later runs.
  - For CV use `sklearn.model_selection.GroupKFold(groups=session_id)`.
  - Keep a **time gap ≥ H** between train and test to avoid horizon bleed.

```python
def make_datasets(cfg) -> tuple[X_train, y_train, X_test, y_test, groups]: ...
```

## B.6 Imbalance, training, tuning — `ml/train.py`
- `none` dominates → pass `sample_weight` (inverse class frequency) or class
  weights. **Judge by macro-F1, per-class recall, PR-AUC, confusion matrix** —
  *never raw accuracy* (a "predict none always" model scores high accuracy and is
  useless).
- Core fit:
  ```python
  model = XGBClassifier(
      objective="multi:softprob", num_class=5, eval_metric="mlogloss",
      n_estimators=, max_depth=, learning_rate=, subsample=,
      colsample_bytree=, min_child_weight=, gamma=, reg_lambda=,
      tree_method="hist", n_jobs=-1)
  model.fit(X_train, y_train, sample_weight=w,
            eval_set=[(X_val, y_val)], early_stopping_rounds=50, verbose=False)
  ```
- Tune with **Optuna** (or `RandomizedSearchCV`) over depth, lr, n_estimators,
  subsample, colsample_bytree, min_child_weight, gamma, reg_lambda, optimizing
  **macro-F1** via the grouped CV from B.5.

## B.7 Evaluation — `ml/evaluate.py` (make it convincing)
- **Per-class** precision / recall / F1 + **macro-F1**; full **confusion matrix**;
  **PR curves** per class.
- **Lead-time analysis** — for each true failure, how many hours before
  `failure_ts` did the model first raise that class? Plot the distribution. *This
  is the metric that proves predictive-maintenance value.*
- **Cost-aware threshold** — a missed failure ≫ a false alarm; pick the operating
  threshold accordingly and report the chosen point.
- **Baselines to beat** — (a) "always `none`", (b) a simple threshold rule
  (e.g. vibration > X). Show the model beats both.
- **SHAP** — global + per-prediction attributions; confirm they match the injected
  fingerprints (bearing→vibration slope, heater→winding_temp, etc.). Great for the
  report and for trust.

## B.8 Model artifact
Persist together so serving (Part C) and the lifecycle (Plan 03) reuse exactly:
- `model.json` via `booster.save_model` (version-stable across XGBoost releases),
- `FEATURE_COLUMNS` (frozen order),
- the label encoder / class order,
- the feature config (`cfg`: H, window sizes, stride) + `pipeline_version`.
In Plan 03 this bundle is logged to MLflow (with a filesystem/object-store backup) and the
training run records its **dataset manifest** (shard list + rolling-window range).

## B.9 Step-by-step (model)
1. Write `ml/config.py` (H, windows, paths, class names).
2. Implement `features.py`; smoke-test on one session's readings.
3. Implement `labels.py`; verify class distribution is sane (every class present).
4. Implement `dataset.py` with **grouped** split; assert no `session_id` appears in
   both train and test.
5. Implement `train.py`; train a first model with class weights + early stopping.
6. Implement `evaluate.py`; produce confusion matrix, per-class recall, lead-time,
   SHAP; compare to baselines.
7. Iterate features/horizon/tuning until acceptance (B.10).
8. Save the artifact bundle (B.8).

## B.10 Model verification & acceptance
- No `session_id` leaks across train/test (assert in code).
- **Macro-F1 and per-class recall** clearly beat "always `none`".
- Confusion matrix shows real diagonal mass for each failure class (not just `none`).
- **Lead-time** median is materially > 0 (model warns *before* failure).
- SHAP attributions match injected fingerprints.

---

# PART C — Serve the model + live frontend display (MAIN USE CASE)

Built **right after** a first acceptable model, **before** the heavy lifecycle.
This is the demo that proves the project: live machine runs stream in and the
dashboard shows the model's predicted maintenance result per machine.

## C.1 Backend — `backend/app/services/prediction_service.py`
```python
_model = None  # cached
def _load_model():        # load artifact bundle (B.8); refresh when version changes
def predict_machine(machine: str) -> dict:
    # 1. pull the latest window of readings for `machine` from MySQL
    #    (select(Reading).where(machine).order_by(Reading.seq.desc()).limit(W))
    # 2. build_feature_row(window, cfg)        ← SAME ml/features.py as training
    # 3. model.predict_proba → class + probabilities
    # 4. derive a lead-time/RUL-ish estimate; log to the `predictions` table
    # 5. return { machine, predicted_class, probabilities, lead_time_h, model_version, ts }
def predict_all() -> list[dict]:               # every machine, sorted by risk
```

## C.2 Routes — `backend/app/routes/prediction.py`
```python
@router.get("/predict/{machine}")  def predict(machine): return predict_machine(machine)
@router.get("/maintenance")        def maintenance():     return predict_all()
@router.get("/model/info")         def model_info():      return current_model_summary()
```
Register the router in `backend/app/main.py`. `/api/maintenance` upgrades the
current rule-based `alerts_service` into **model-driven** alerts.

## C.3 Predictions logging
Every scored reading → `predictions` **table**
`{ ts, session_id, seq, predicted_class, probabilities (JSON), model_version }`.
This is what Plan 03's monitoring/feedback loop consumes (kept forever — small, never pruned).

## C.4 Frontend
- **Per-machine maintenance-risk badge/card** on each live machine run: predicted
  component, probability, and "≈ X h to likely failure".
- A **maintenance panel** listing at-risk machines sorted by risk.
- Place it **beside the OEE graph** so a run shows efficiency *and* predicted
  health together. Reuse existing fetch/polling patterns.

## C.5 Serving verification
- `/api/maintenance` returns one entry per live machine with class + probabilities.
- As the live stream runs, badges update and the **`predictions` table fills**.
- Drive a machine toward failure (raise `GEN_ACCEL`): its predicted class flips to
  the correct component **before** the failure event lands in `machine_runs`.

---

## Pitfalls (whole document)
- **Train/serve skew** — Part C must import the *same* `ml/features.py`; never
  re-implement feature math in the backend.
- **Leakage** — exclude `_truth.*`; use grouped/time splits; keep the H gap.
- **Accuracy trap** — report macro-F1 / per-class recall / lead-time, not accuracy.
- **OEE divide-by-zero** — guard empty buckets (prior `toFixed` crash class).
- **Artifact drift** — persist `FEATURE_COLUMNS` + config with the model so serving
  and retraining stay consistent.
