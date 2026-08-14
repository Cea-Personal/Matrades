from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.shared.events import OutboxEvent, OutboxState


def claim_pending(session: Session, limit: int = 100) -> list[OutboxEvent]:
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.state == OutboxState.PENDING)
        .order_by(
            OutboxEvent.aggregate_type,
            OutboxEvent.aggregate_id,
            OutboxEvent.aggregate_version,
            OutboxEvent.created_at,
        )
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    return list(session.scalars(statement))


def dispatch_claimed(
    session: Session,
    events: list[OutboxEvent],
    publish: Callable[[dict[str, object]], None],
    now: datetime,
) -> None:
    for event in events:
        try:
            publish(event.envelope)
        except Exception as error:  # pragma: no cover - provider-specific failures
            event.attempts += 1
            event.state = OutboxState.FAILED
            event.last_error = str(error)[:1000]
        else:
            event.attempts += 1
            event.state = OutboxState.PUBLISHED
            event.published_at = now
