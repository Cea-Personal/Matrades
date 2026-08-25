"""Per-account research schedule normalization and due-time calculations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_WEEKDAYS = [0, 1, 2, 3, 4, 5, 6]


def default_schedule(
    *, enabled: bool, run_at: str, timezone: str = "UTC"
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "run_at": run_at,
        "timezone": timezone,
        "weekdays": list(DEFAULT_WEEKDAYS),
    }


def schedule_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown schedule timezone: {value}") from exc


def _parse_run_at(value: str) -> tuple[int, int]:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError("run_at must use HH:MM 24-hour format") from exc
    return parsed.hour, parsed.minute


def normalize_schedule(
    value: dict[str, Any] | None, *, fallback: dict[str, Any]
) -> dict[str, Any]:
    source = {**fallback, **(value or {})}
    enabled = bool(source.get("enabled", fallback["enabled"]))
    run_at = str(source.get("run_at", fallback["run_at"]))
    _parse_run_at(run_at)
    timezone = str(source.get("timezone", fallback["timezone"]))
    schedule_timezone(timezone)
    raw_weekdays = source.get("weekdays", DEFAULT_WEEKDAYS)
    weekdays = sorted({int(day) for day in raw_weekdays})
    if any(day < 0 or day > 6 for day in weekdays):
        raise ValueError("weekdays must contain values from 0 (Monday) through 6 (Sunday)")
    if enabled and not weekdays:
        raise ValueError("an enabled schedule must include at least one weekday")
    return {
        "enabled": enabled,
        "run_at": run_at,
        "timezone": timezone,
        "weekdays": weekdays,
    }


def is_due(schedule: dict[str, Any], *, now: datetime | None = None) -> bool:
    if not schedule.get("enabled", False):
        return False
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    local_now = observed_at.astimezone(schedule_timezone(str(schedule["timezone"])))
    hour, minute = _parse_run_at(str(schedule["run_at"]))
    return (
        local_now.weekday() in schedule["weekdays"]
        and (local_now.hour, local_now.minute) >= (hour, minute)
    )


def next_run_at(
    schedule: dict[str, Any], *, now: datetime | None = None
) -> datetime | None:
    if not schedule.get("enabled", False):
        return None
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    timezone = schedule_timezone(str(schedule["timezone"]))
    local_now = observed_at.astimezone(timezone)
    hour, minute = _parse_run_at(str(schedule["run_at"]))
    for offset in range(8):
        candidate_date = local_now.date() + timedelta(days=offset)
        candidate = datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            hour,
            minute,
            tzinfo=timezone,
        )
        if candidate.weekday() in schedule["weekdays"] and candidate >= local_now:
            return candidate.astimezone(UTC)
    return None
