from datetime import UTC, datetime

import pytest

from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.types import InvalidTransition
from traderx_worker.runtime.jobs import checkpoint, request_cancel


def test_job_cancel_is_safe_and_durable() -> None:
    job = BackgroundJob(job_type="test", context={}, input_manifest={}, progress={})
    now = datetime(2026, 8, 12, tzinfo=UTC)
    request_cancel(job, now)
    job.state = JobState.RUNNING
    checkpoint(job, completed=0, total=1, message="safe", now=now)
    assert job.state == JobState.CANCELLED


def test_job_progress_pause_resume_and_retry_follow_durable_state_machine() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    job = BackgroundJob(job_type="research", context={}, input_manifest={}, progress={})
    job.state = JobState.RUNNING
    checkpoint(job, completed=3, total=10, message="batch three committed", now=now)
    assert job.progress["completed_units"] == 3
    job.pause_requested_at = now
    checkpoint(job, completed=4, total=10, message="safe checkpoint", now=now)
    assert job.state == JobState.PAUSED
    job.transition(JobState.QUEUED)
    job.pause_requested_at = None
    job.transition(JobState.RUNNING)
    job.transition(JobState.FAILED)
    job.transition(JobState.QUEUED)
    assert job.state == JobState.QUEUED
    with pytest.raises(InvalidTransition):
        job.transition(JobState.COMPLETED)


def test_browser_disconnect_cannot_cancel_a_job_without_an_explicit_request() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    job = BackgroundJob(job_type="research", context={}, input_manifest={}, progress={})
    job.state = JobState.RUNNING
    checkpoint(job, completed=5, total=10, message="browser absent", now=now)
    assert job.state == JobState.RUNNING
    assert job.cancel_requested_at is None
