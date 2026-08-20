"""Deterministic calendar gate for new live recommendations only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.market_data.model import CalendarCoverage, EconomicEvent, EventRiskPolicyVersion


@dataclass(frozen=True, slots=True)
class EventGuardResult:
    blocked: bool
    reason_codes: tuple[str, ...]
    blocks: tuple[dict[str, object], ...]


def evaluate_event_guard(
    database: Session, *, account_id: UUID, category: str, instrument_id: UUID | None, now: datetime
) -> EventGuardResult:
    policy = database.scalar(
        select(EventRiskPolicyVersion)
        .where(EventRiskPolicyVersion.account_id == account_id, EventRiskPolicyVersion.retired_at.is_(None))
        .order_by(EventRiskPolicyVersion.effective_from.desc()).limit(1)
    )
    if policy is None:
        return EventGuardResult(False, (), ())
    # Scraped experimental events are visible for development inspection only.
    # They must never influence a deterministic live recommendation gate.
    due = list(
        database.scalars(
            select(EconomicEvent).where(
                EconomicEvent.impact == "HIGH",
                EconomicEvent.status != "CANCELLED",
                EconomicEvent.source_origin.in_(("OFFICIAL_MACHINE", "OWNER_CITED")),
            )
        )
    )
    blocks: list[dict[str, object]] = []
    at = _aware(now)
    for event in due:
        if event.canonical_type not in policy.enabled_event_types:
            continue
        if category not in event.affected_categories and (not instrument_id or str(instrument_id) not in event.affected_instruments):
            continue
        event_at = _aware(event.scheduled_at or event.event_at)
        starts = event_at - timedelta(minutes=policy.pre_buffer_minutes)
        ends = event_at + timedelta(minutes=policy.post_buffer_minutes)
        if starts <= at <= ends:
            blocks.append({"event_id": str(event.id), "state": "IN_GUARD_WINDOW", "remaining_seconds": max(0, int((ends - at).total_seconds())), "official_url": event.source_url})
    if policy.coverage_required and _coverage_degraded(database, category=category, now=at):
        blocks.append({"event_id": "coverage", "state": "CALENDAR_COVERAGE_DEGRADED", "remaining_seconds": 0, "official_url": ""})
    reasons = tuple(sorted({str(item["state"]) for item in blocks}))
    return EventGuardResult(bool(blocks), reasons, tuple(blocks))


def _coverage_degraded(database: Session, *, category: str, now: datetime) -> bool:
    rows = list(database.scalars(select(CalendarCoverage)))
    # An empty catalogue is not an implicit pass once the owner enabled this gate.
    if not rows:
        return True
    return any(
        row.status not in {"VERIFIED", "HEALTHY"}
        or row.covered_through is None
        or _aware(row.covered_through) < now
        for row in rows
        if row.scope_key in {"GLOBAL", category}
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
