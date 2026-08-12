from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, CreatedAtMixin, IdentifiedMixin


class OutboxState(StrEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class OutboxEvent(IdentifiedMixin, Base):
    __tablename__ = "outbox_events"

    aggregate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    aggregate_version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(180), nullable=False)
    envelope: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=OutboxState.PENDING, nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class ConsumerReceipt(CreatedAtMixin, Base):
    __tablename__ = "consumer_receipts"
    __table_args__ = (
        UniqueConstraint("consumer_name", "event_source", "event_id", name="consumer_event"),
    )

    consumer_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    event_source: Mapped[str] = mapped_column(String(180), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)


def event_envelope(
    *,
    source: str,
    event_type: str,
    subject: str,
    data: dict[str, Any],
    now: datetime,
    correlation_id: str,
    causation_id: str | None = None,
    actor_id: UUID | None = None,
    aggregate_version: int = 1,
) -> dict[str, Any]:
    return {
        "specversion": "1.0",
        "id": str(uuid4()),
        "source": source,
        "type": event_type,
        "subject": subject,
        "time": now.isoformat(),
        "datacontenttype": "application/json",
        "correlationid": correlation_id,
        "causationid": causation_id,
        "actorid": str(actor_id) if actor_id else None,
        "aggregateversion": aggregate_version,
        "data": data,
    }


def append_outbox(
    session: Any,
    *,
    aggregate_type: str,
    aggregate_id: UUID,
    aggregate_version: int,
    event_type: str,
    envelope: dict[str, Any],
) -> OutboxEvent:
    event = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        envelope=envelope,
    )
    session.add(event)
    return event
