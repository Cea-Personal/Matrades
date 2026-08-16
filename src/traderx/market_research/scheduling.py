from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.market_research.events import (
    OCCURRENCE_CLAIMED,
    OCCURRENCE_OVERLAP_SKIPPED,
    emit_market_research_fact,
)
from traderx.market_research.model import MarketResearchOccurrence, MarketResearchSchedule

MIN_INTERVAL_SECONDS = 3600
MAX_INTERVAL_SECONDS = 30 * 24 * 60 * 60


def next_due_at(
    *,
    anchored_start_local: datetime,
    account_timezone: str,
    interval_seconds: int,
    after: datetime,
) -> datetime:
    if not MIN_INTERVAL_SECONDS <= interval_seconds <= MAX_INTERVAL_SECONDS:
        raise ValueError("market research interval must be between one hour and 30 days")
    if anchored_start_local.tzinfo is None or after.tzinfo is None:
        raise ValueError("schedule times must be timezone-aware")
    try:
        timezone = ZoneInfo(account_timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("account_timezone must be a valid IANA time zone") from error

    local_anchor = anchored_start_local.astimezone(timezone)
    local_after = after.astimezone(timezone)
    # Preserve wall-clock anchors for whole-day schedules, including DST boundaries.
    if interval_seconds % 86400 == 0:
        interval_days = interval_seconds // 86400
        elapsed_days = max(0, (local_after.date() - local_anchor.date()).days)
        occurrence = max(0, math.floor(elapsed_days / interval_days))
        naive_anchor = local_anchor.replace(tzinfo=None)
        candidate = (naive_anchor + timedelta(days=occurrence * interval_days)).replace(
            tzinfo=timezone
        )
        while candidate <= local_after:
            occurrence += 1
            candidate = (naive_anchor + timedelta(days=occurrence * interval_days)).replace(
                tzinfo=timezone
            )
        return candidate.astimezone(UTC)

    anchor_utc = local_anchor.astimezone(UTC)
    after_utc = after.astimezone(UTC)
    elapsed = max(0, (after_utc - anchor_utc).total_seconds())
    occurrence = max(0, math.floor(elapsed / interval_seconds) + 1)
    candidate = anchor_utc + timedelta(seconds=occurrence * interval_seconds)
    if candidate <= after_utc:
        candidate += timedelta(seconds=interval_seconds)
    return candidate


def claim_occurrence(
    database: Session,
    schedule: MarketResearchSchedule,
    *,
    scheduled_for: datetime,
    claimed_at: datetime,
    active_run_id: UUID | None = None,
    lease_owner: str | None = None,
    lease_token: str | None = None,
    lease_duration: timedelta = timedelta(minutes=10),
    correlation_id: str = "market-research-scheduler",
) -> MarketResearchOccurrence:
    existing = database.scalar(
        select(MarketResearchOccurrence).where(
            MarketResearchOccurrence.schedule_id == schedule.id,
            MarketResearchOccurrence.scheduled_for == scheduled_for,
        )
    )
    if existing is not None:
        return existing
    state = "SKIPPED_OVERLAP" if active_run_id is not None else "CLAIMED"
    occurrence = MarketResearchOccurrence(
        schedule_id=schedule.id,
        scheduled_for=scheduled_for,
        state=state,
        active_run_id=active_run_id,
        reason="PREVIOUS_COORDINATED_RUN_ACTIVE" if active_run_id is not None else None,
        claimed_at=claimed_at,
        lease_owner=lease_owner,
        lease_token=lease_token,
        lease_expires_at=claimed_at + lease_duration if lease_token is not None else None,
    )
    database.add(occurrence)
    schedule.last_due_at = scheduled_for
    # No catch-up: advance from the claim time if the scanner was late.
    schedule.next_run_at = next_due_at(
        anchored_start_local=schedule.anchored_start_local,
        account_timezone=schedule.account_timezone,
        interval_seconds=schedule.interval_seconds,
        after=max(claimed_at, scheduled_for),
    )
    database.flush()
    emit_market_research_fact(
        database,
        aggregate_type="market_research_occurrence",
        aggregate_id=occurrence.id,
        aggregate_version=occurrence.version,
        event_type=(
            OCCURRENCE_OVERLAP_SKIPPED
            if state == "SKIPPED_OVERLAP"
            else OCCURRENCE_CLAIMED
        ),
        data={
            "schedule_id": str(schedule.id),
            "scheduled_for": scheduled_for.isoformat(),
            "state": state,
            "active_run_id": str(active_run_id) if active_run_id else None,
            "reason": occurrence.reason,
        },
        now=claimed_at,
        correlation_id=correlation_id,
    )
    return occurrence


def recover_expired_lease(
    occurrence: MarketResearchOccurrence,
    *,
    now: datetime,
    lease_owner: str,
    lease_token: str,
    lease_duration: timedelta = timedelta(minutes=10),
) -> bool:
    if occurrence.state != "CLAIMED" or (
        occurrence.lease_expires_at is not None and occurrence.lease_expires_at > now
    ):
        return False
    occurrence.lease_owner = lease_owner
    occurrence.lease_token = lease_token
    occurrence.lease_expires_at = now + lease_duration
    return True
