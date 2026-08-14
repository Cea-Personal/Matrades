from __future__ import annotations

from uuid import UUID

from celery import shared_task
from sqlalchemy.orm import Session

from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.types import InvalidTransition, utc_now
from traderx.validation.service import execute_backtest, execute_validation
from traderx_worker.runtime.jobs import checkpoint
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.validation.run", bind=True, acks_late=True)
def run_validation(
    self: object,
    strategy_version_id: str,
    manifest_hash: str,
    background_job_id: str | None = None,
) -> dict[str, str]:
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if _stop_requested(job, completed=0, total=3, message="Starting chronological replay"):
            return {"strategy_version_id": strategy_version_id, "manifest_hash": manifest_hash, "run_id": "", "status": _job_status(job)}
        backtest = execute_backtest(
            database,
            strategy_version_id=UUID(strategy_version_id),
            requested_manifest_hash=manifest_hash,
        )
        if _stop_requested(job, completed=1, total=3, message="Backtest evidence persisted"):
            return {"strategy_version_id": strategy_version_id, "manifest_hash": manifest_hash, "run_id": str(backtest.id), "status": _job_status(job)}
        validation = execute_validation(
            database,
            strategy_version_id=UUID(strategy_version_id),
            backtest_run_id=backtest.id,
            seed=20260813,
            requested_manifest_hash=manifest_hash,
        )
        run_id = str(validation.id)
        state = str(validation.state)
        _complete_job(job, run_id, f"/api/v1/validation/runs/{run_id}")
    return {
        "strategy_version_id": strategy_version_id,
        "manifest_hash": manifest_hash,
        "run_id": run_id,
        "status": state,
    }


@shared_task(name="traderx.backtest.run", bind=True, acks_late=True)
def run_backtest(
    self: object,
    strategy_version_id: str,
    manifest_hash: str,
    background_job_id: str | None = None,
) -> dict[str, str]:
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if _stop_requested(job, completed=0, total=2, message="Starting chronological replay"):
            return {"strategy_version_id": strategy_version_id, "manifest_hash": manifest_hash, "run_id": "", "status": _job_status(job)}
        backtest = execute_backtest(
            database,
            strategy_version_id=UUID(strategy_version_id),
            requested_manifest_hash=manifest_hash,
        )
        run_id = str(backtest.id)
        state = str(backtest.state)
        _complete_job(job, run_id, f"/api/v1/validation/backtests/{run_id}")
    return {
        "strategy_version_id": strategy_version_id,
        "manifest_hash": manifest_hash,
        "run_id": run_id,
        "status": state,
    }


def _start_job(database: Session, background_job_id: str | None) -> BackgroundJob | None:
    if background_job_id is None:
        return None
    job = database.get(BackgroundJob, UUID(background_job_id))
    if job is None:
        raise InvalidTransition("the durable validation job does not exist")
    if JobState(job.state or JobState.QUEUED) == JobState.QUEUED:
        job.transition(JobState.RUNNING)
        job.started_at = utc_now()
        job.attempt_count += 1
    if JobState(job.state) != JobState.RUNNING:
        raise InvalidTransition("the durable validation job is not runnable")
    return job


def _stop_requested(
    job: BackgroundJob | None, *, completed: int, total: int, message: str
) -> bool:
    if job is None:
        return False
    checkpoint(job, completed=completed, total=total, message=message, now=utc_now())
    return job.state in {JobState.CANCELLED, JobState.PAUSED}


def _complete_job(job: BackgroundJob | None, run_id: str, result_ref: str) -> None:
    if job is None:
        return
    checkpoint(job, completed=1, total=1, message="Evidence completed", now=utc_now())
    job.transition(JobState.COMPLETED)
    job.finished_at = utc_now()
    job.result_ref = result_ref
    job.progress = {**job.progress, "run_id": run_id}


def _job_status(job: BackgroundJob | None) -> str:
    if job is None:
        raise InvalidTransition("a stopped task must have a durable job")
    return str(job.state)
