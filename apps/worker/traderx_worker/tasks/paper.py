from __future__ import annotations

from uuid import UUID

from celery import shared_task
from sqlalchemy.orm import Session

from traderx.jobs.model import BackgroundJob, JobState
from traderx.paper.model import PaperRun
from traderx.paper.service import execute_paper_run
from traderx.shared.types import InvalidTransition, utc_now
from traderx_worker.runtime.jobs import checkpoint
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.paper.evaluate", bind=True, acks_late=True)
def evaluate_paper_run(
    self: object, paper_run_id: str, background_job_id: str | None = None
) -> dict[str, str]:
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if _checkpoint_stopped(job, 0, 1, "Evaluating paper evidence"):
            return {"paper_run_id": paper_run_id, "status": _job_status(job)}
        run = database.get(PaperRun, UUID(paper_run_id))
        if run is None:
            return {"paper_run_id": paper_run_id, "status": "MISSING"}
        _complete_job(job, run.id)
        return {
            "paper_run_id": paper_run_id,
            "status": str(run.state),
            "evidence_hash": run.evidence_hash,
        }


@shared_task(name="traderx.paper.start", bind=True, acks_late=True)
def start_paper_evaluation(
    self: object,
    strategy_version_id: str,
    validation_run_id: str,
    evidence_manifest_hash: str,
    background_job_id: str | None = None,
) -> dict[str, str]:
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if _checkpoint_stopped(job, 0, 3, "Freezing current-data inputs"):
            return {"paper_run_id": "", "status": _job_status(job)}
        run = execute_paper_run(
            database,
            strategy_version_id=UUID(strategy_version_id),
            validation_run_id=UUID(validation_run_id),
            evidence_manifest_hash=evidence_manifest_hash,
        )
        if _checkpoint_stopped(job, 2, 3, "Paper fills and journal projection persisted"):
            return {"paper_run_id": str(run.id), "status": _job_status(job)}
        _complete_job(job, run.id)
        return {
            "paper_run_id": str(run.id),
            "status": str(run.state),
            "evidence_hash": run.evidence_hash,
        }


def _start_job(database: Session, background_job_id: str | None) -> BackgroundJob | None:
    if background_job_id is None:
        return None
    job = database.get(BackgroundJob, UUID(background_job_id))
    if job is None:
        raise InvalidTransition("the durable paper job does not exist")
    if JobState(job.state or JobState.QUEUED) == JobState.QUEUED:
        job.transition(JobState.RUNNING)
        job.started_at = utc_now()
        job.attempt_count += 1
    if JobState(job.state) != JobState.RUNNING:
        raise InvalidTransition("the durable paper job is not runnable")
    return job


def _checkpoint_stopped(
    job: BackgroundJob | None, completed: int, total: int, message: str
) -> bool:
    if job is None:
        return False
    checkpoint(job, completed=completed, total=total, message=message, now=utc_now())
    return job.state in {JobState.CANCELLED, JobState.PAUSED}


def _complete_job(job: BackgroundJob | None, run_id: UUID) -> None:
    if job is None:
        return
    checkpoint(job, completed=1, total=1, message="Paper evaluation completed", now=utc_now())
    job.transition(JobState.COMPLETED)
    job.finished_at = utc_now()
    job.result_ref = f"/api/v1/paper/runs/{run_id}"


def _job_status(job: BackgroundJob | None) -> str:
    if job is None:
        raise InvalidTransition("a stopped task must have a durable job")
    return str(job.state)
