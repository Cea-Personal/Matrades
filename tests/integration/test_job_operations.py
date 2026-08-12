from datetime import UTC, datetime

from traderx.jobs.model import BackgroundJob, JobState
from traderx_worker.runtime.jobs import checkpoint, request_cancel


def test_job_cancel_is_safe_and_durable() -> None:
    job = BackgroundJob(job_type="test", context={}, input_manifest={}, progress={})
    now = datetime(2026, 8, 12, tzinfo=UTC)
    request_cancel(job, now)
    job.state = JobState.RUNNING
    checkpoint(job, completed=0, total=1, message="safe", now=now)
    assert job.state == JobState.CANCELLED
