from apps.worker.app.celery_app import celery_app
from apps.worker.app.tasks.research import run_research_cycle, schedule_research_cycles


def test_per_account_research_is_checked_every_minute_and_accepts_no_caller_candidates() -> None:
    schedule = celery_app.conf.beat_schedule["per-account-autonomous-research"]

    assert schedule["task"] == schedule_research_cycles.name
    assert run_research_cycle.name.endswith("run_research_cycle")
    assert "candidates" not in run_research_cycle.run.__annotations__


def test_research_schedule_normalizes_timezone_and_due_time() -> None:
    from datetime import UTC, datetime

    from modules.research.scheduling import is_due, next_run_at, normalize_schedule

    schedule = normalize_schedule(
        {"enabled": True, "run_at": "09:30", "timezone": "Africa/Kigali", "weekdays": [0]},
        fallback={
            "enabled": True,
            "run_at": "05:00",
            "timezone": "UTC",
            "weekdays": list(range(7)),
        },
    )
    observed = datetime(2026, 8, 24, 7, 0, tzinfo=UTC)

    assert not is_due(schedule, now=observed)
    assert next_run_at(schedule, now=observed).isoformat() == "2026-08-24T07:30:00+00:00"
    assert is_due(schedule, now=datetime(2026, 8, 24, 8, 0, tzinfo=UTC))
