from __future__ import annotations

from uuid import UUID

from celery import shared_task
from sqlalchemy.orm import Session

from traderx.jobs.model import BackgroundJob, JobState
from traderx.market_research.service import execute_market_research, refresh_mt5_instrument_catalog
from traderx.shared.types import InvalidTransition, utc_now
from traderx_worker.runtime.jobs import checkpoint
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.market_data.sync", bind=True, acks_late=True)
def synchronize_market_data(
    self: object,
    provider: str,
    cursor: str | None = None,
    background_job_id: str | None = None,
) -> dict[str, str | None]:
    if provider != "MT5_TERMINAL_BRIDGE":
        return {"provider": provider, "cursor": cursor, "status": "REJECTED_UNAPPROVED_PROVIDER"}
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if job is not None:
            checkpoint(
                job,
                completed=0,
                total=1,
                message="Refreshing the broker instrument catalog",
                now=utc_now(),
            )
            if job.state in {JobState.CANCELLED, JobState.PAUSED}:
                return {"provider": provider, "cursor": cursor, "status": str(job.state)}
        imported = refresh_mt5_instrument_catalog(database)
        if job is not None:
            checkpoint(
                job,
                completed=1,
                total=1,
                message="Broker instrument catalog refreshed",
                now=utc_now(),
            )
            job.transition(JobState.COMPLETED)
            job.finished_at = utc_now()
            job.result_ref = f"market-data:{provider}:{cursor or 'full'}"
    return {
        "provider": provider,
        "cursor": cursor,
        "status": "COMPLETED",
        "imported": str(imported),
    }


@shared_task(name="traderx.market_research.run", bind=True, acks_late=True)
def run_market_research(
    self: object, category: str, background_job_id: str | None = None
) -> dict[str, str]:
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if job is not None:
            checkpoint(
                job,
                completed=0,
                total=2,
                message="Evaluating mandatory eligibility gates",
                now=utc_now(),
            )
            if job.state in {JobState.CANCELLED, JobState.PAUSED}:
                return {"category": category, "run_id": "", "status": str(job.state)}
        run = execute_market_research(
            database, category=category, method_version="market-suitability-v1"
        )
        run_id = str(run.id)
        if job is not None:
            checkpoint(
                job,
                completed=2,
                total=2,
                message="Immutable research report completed",
                now=utc_now(),
            )
            job.transition(JobState.COMPLETED)
            job.finished_at = utc_now()
            job.result_ref = f"/api/v1/markets/research/{run_id}"
    return {"category": category, "run_id": run_id, "status": "COMPLETED"}


def _start_job(database: Session, background_job_id: str | None) -> BackgroundJob | None:
    if background_job_id is None:
        return None
    job = database.get(BackgroundJob, UUID(background_job_id))
    if job is None:
        raise InvalidTransition("the durable market job does not exist")
    if JobState(job.state or JobState.QUEUED) == JobState.QUEUED:
        job.transition(JobState.RUNNING)
        job.started_at = utc_now()
        job.attempt_count += 1
    if JobState(job.state) != JobState.RUNNING:
        raise InvalidTransition("the durable market job is not runnable")
    return job
