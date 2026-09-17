"""Lifecycle scheduler (Plan 03 Part C.2) — drives seal + retrain together.

Jobs (APScheduler, standalone worker process):
  01:00 nightly   seal_and_prune            (Part A.2)
  02:00 nightly   retrain                   (subprocess: python -m ml.train)
  every 6 h       drift check               → retrain when flagged (Part D)
  every 6 h       volume check              → retrain when ≥ K new failures
                                              landed since the last training run
  every 1 h       feedback loop             (Part E)

Retraining runs in a SUBPROCESS so its memory is fully released afterwards and
a crash can't take the scheduler down.  A cooldown stops drift/volume triggers
from stacking retrains on top of each other.

Env knobs: SEAL_HOUR, RETRAIN_HOUR, DRIFT_EVERY_H, FEEDBACK_EVERY_H,
RETRAIN_MIN_NEW_FAILURES, RETRAIN_COOLDOWN_H.

CLI
---
  python -m ml.schedule                 # run the scheduler (blocking)
  python -m ml.schedule --once seal     # run one job now and exit
  python -m ml.schedule --once retrain | drift | feedback | volume
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

import ml.config as cfg
from ml.db import get_engine
from ml.tables import ensure_tables

SEAL_HOUR        = int(os.getenv("SEAL_HOUR", "1"))
RETRAIN_HOUR     = int(os.getenv("RETRAIN_HOUR", "2"))
DRIFT_EVERY_H    = int(os.getenv("DRIFT_EVERY_H", "6"))
FEEDBACK_EVERY_H = int(os.getenv("FEEDBACK_EVERY_H", "1"))
MIN_NEW_FAILURES = int(os.getenv("RETRAIN_MIN_NEW_FAILURES", "3"))
COOLDOWN_H       = float(os.getenv("RETRAIN_COOLDOWN_H", "12"))

_REPO_ROOT = Path(__file__).parent.parent
_last_retrain_at: datetime | None = None


def _log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ── Jobs ──────────────────────────────────────────────────────────────────────

def job_seal_and_prune() -> None:
    _log("job: seal_and_prune starting")
    try:
        from ml.retention import seal_and_prune
        seal_and_prune()
    except Exception as e:
        _log(f"job: seal_and_prune FAILED: {e}")


def _cooldown_ok() -> bool:
    global _last_retrain_at
    if _last_retrain_at is None:
        # Also respect the last registered training run across restarts
        try:
            engine = get_engine()
            ensure_tables(engine)
            with engine.connect() as conn:
                t = conn.execute(text(
                    "SELECT MAX(trained_at) FROM model_registry")).scalar()
            if t is not None:
                _last_retrain_at = t if isinstance(t, datetime) else None
        except Exception:
            pass
    if _last_retrain_at is None:
        return True
    return datetime.now(timezone.utc).replace(tzinfo=None) - _last_retrain_at \
        >= timedelta(hours=COOLDOWN_H)


def job_retrain(reason: str = "scheduled") -> None:
    """Run the full retraining pipeline in a subprocess (memory isolation)."""
    global _last_retrain_at
    if reason != "scheduled" and not _cooldown_ok():
        _log(f"job: retrain ({reason}) skipped — cooldown ({COOLDOWN_H}h) active")
        return

    _log(f"job: retrain starting (reason={reason})")
    env = {**os.environ, "PYTHONUTF8": "1"}
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "ml.train", "--reset"],
        cwd=str(_REPO_ROOT), env=env,
        capture_output=True, text=True,
    )
    _last_retrain_at = datetime.now(timezone.utc).replace(tzinfo=None)
    tail = "\n".join((proc.stdout or "").splitlines()[-15:])
    _log(f"job: retrain finished rc={proc.returncode} in {time.time()-t0:.0f}s\n{tail}")
    if proc.returncode != 0:
        _log(f"job: retrain stderr tail:\n"
             + "\n".join((proc.stderr or "").splitlines()[-15:]))


def job_drift() -> None:
    _log("job: drift check starting")
    try:
        from ml.drift import check_drift
        summary = check_drift()
        if summary.get("retrain_recommended"):
            _log("job: drift flagged significant shift — triggering retrain")
            job_retrain(reason="drift")
    except Exception as e:
        _log(f"job: drift FAILED: {e}")


def job_volume() -> None:
    """Volume trigger — retrain when ≥ K new failure events landed since the
    last training run (compares machine_runs.failure_ts to the last
    model_registry.trained_at; sim time ≈ wall time once the live stream runs)."""
    try:
        engine = get_engine()
        ensure_tables(engine)
        with engine.connect() as conn:
            last = conn.execute(text(
                "SELECT MAX(trained_at) FROM model_registry")).scalar()
            if last is None:
                return
            n = conn.execute(text(
                "SELECT COUNT(*) FROM machine_runs "
                "WHERE failure_ts IS NOT NULL AND failure_ts > :t"
            ), {"t": last}).scalar()
        if int(n) >= MIN_NEW_FAILURES:
            _log(f"job: volume trigger — {n} new failures since last train")
            job_retrain(reason="volume")
    except Exception as e:
        _log(f"job: volume check FAILED: {e}")


def job_feedback() -> None:
    _log("job: feedback loop starting")
    try:
        from ml.feedback import evaluate_live_outcomes
        evaluate_live_outcomes(window_days=7)
    except Exception as e:
        _log(f"job: feedback FAILED: {e}")


# ── Scheduler ─────────────────────────────────────────────────────────────────

def build_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler

    sched = BlockingScheduler(timezone="UTC")
    common = dict(coalesce=True, max_instances=1, misfire_grace_time=3600)

    sched.add_job(job_seal_and_prune, "cron", hour=SEAL_HOUR,
                  id="seal_and_prune", **common)
    sched.add_job(job_retrain, "cron", hour=RETRAIN_HOUR,
                  id="retrain_nightly", kwargs={"reason": "scheduled"}, **common)
    sched.add_job(job_drift, "interval", hours=DRIFT_EVERY_H,
                  id="drift_check", **common)
    sched.add_job(job_volume, "interval", hours=DRIFT_EVERY_H,
                  id="volume_check", **common)
    sched.add_job(job_feedback, "interval", hours=FEEDBACK_EVERY_H,
                  id="feedback_loop", **common)
    return sched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", choices=["seal", "retrain", "drift", "feedback", "volume"],
                        help="run a single job now and exit")
    parser.add_argument("--list", action="store_true", help="print jobs and exit")
    args = parser.parse_args()

    if args.once:
        {"seal": job_seal_and_prune, "retrain": job_retrain,
         "drift": job_drift, "feedback": job_feedback,
         "volume": job_volume}[args.once]()
        return

    sched = build_scheduler()
    if args.list:
        for j in sched.get_jobs():
            print(f"  {j.id:16s} trigger={j.trigger}")
        return

    _log(f"scheduler starting: seal@{SEAL_HOUR:02d}:00, retrain@{RETRAIN_HOUR:02d}:00, "
         f"drift/volume every {DRIFT_EVERY_H}h, feedback every {FEEDBACK_EVERY_H}h (UTC)")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        _log("scheduler stopped")


if __name__ == "__main__":
    main()
