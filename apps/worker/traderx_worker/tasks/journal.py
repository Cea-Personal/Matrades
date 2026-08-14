from __future__ import annotations

from uuid import UUID

from celery import shared_task
from sqlalchemy.orm import Session

from traderx.jobs.model import BackgroundJob, JobState
from traderx.journal.analytics import aggregate_all_dimensions
from traderx.journal.projector import project_completed_activity
from traderx.shared.types import InvalidTransition, utc_now
from traderx_worker.runtime.jobs import checkpoint
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.journal.project_close", bind=True, acks_late=True)
def project_trade_close(
    self: object, trade_id: str, background_job_id: str | None = None
) -> dict[str, str]:
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if _stopped(job, 0, 2, "Projecting completed broker and paper activity"):
            return {"trade_id": trade_id, "status": _job_status(job), "created": "0"}
        created = project_completed_activity(database)
        aggregate_all_dimensions(database)
        _complete(job, f"journal:{trade_id}")
    return {"trade_id": trade_id, "status": "COMPLETED", "created": str(len(created))}


@shared_task(name="traderx.journal.aggregate", bind=True, acks_late=True)
def aggregate_journal(
    self: object, background_job_id: str | None = None
) -> dict[str, str]:
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if _stopped(job, 0, 10, "Computing governed journal dimensions"):
            return {"status": _job_status(job), "dimensions": "0"}
        results = aggregate_all_dimensions(database)
        _complete(job, "journal-analytics:all")
    return {"status": "COMPLETED", "dimensions": str(len(results))}


def _start_job(database: Session, background_job_id: str | None) -> BackgroundJob | None:
    if background_job_id is None:
        return None
    job = database.get(BackgroundJob, UUID(background_job_id))
    if job is None:
        raise InvalidTransition("the durable journal job does not exist")
    if JobState(job.state or JobState.QUEUED) == JobState.QUEUED:
        job.transition(JobState.RUNNING)
        job.started_at = utc_now()
        job.attempt_count += 1
    if JobState(job.state) != JobState.RUNNING:
        raise InvalidTransition("the durable journal job is not runnable")
    return job


def _stopped(job: BackgroundJob | None, completed: int, total: int, message: str) -> bool:
    if job is None:
        return False
    checkpoint(job, completed=completed, total=total, message=message, now=utc_now())
    return job.state in {JobState.CANCELLED, JobState.PAUSED}


def _complete(job: BackgroundJob | None, result_ref: str) -> None:
    if job is None:
        return
    checkpoint(job, completed=1, total=1, message="Journal evidence completed", now=utc_now())
    job.transition(JobState.COMPLETED)
    job.finished_at = utc_now()
    job.result_ref = result_ref


def _job_status(job: BackgroundJob | None) -> str:
    if job is None:
        raise InvalidTransition("a stopped task must have a durable job")
    return str(job.state)
