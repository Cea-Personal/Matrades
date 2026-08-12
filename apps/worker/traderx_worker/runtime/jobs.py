from __future__ import annotations

from datetime import datetime

from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.types import InvalidTransition


def request_cancel(job: BackgroundJob, now: datetime) -> None:
    if JobState(job.state or JobState.QUEUED) in {JobState.COMPLETED, JobState.CANCELLED}:
        raise InvalidTransition("completed or cancelled jobs cannot be cancelled")
    job.cancel_requested_at = now


def checkpoint(
    job: BackgroundJob, *, completed: int, total: int, message: str, now: datetime
) -> None:
    if job.cancel_requested_at is not None:
        job.transition(JobState.CANCELLED)
        job.finished_at = now
        return
    if job.pause_requested_at is not None:
        job.transition(JobState.PAUSED)
        return
    job.progress = {
        "completed_units": completed,
        "total_units": total,
        "message": message,
        "heartbeat_at": now.isoformat(),
    }
