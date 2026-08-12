from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin
from traderx.shared.types import DomainError


class IdempotencyState(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"


class IdempotencyRecord(IdentifiedMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_id", "operation", "key", name="actor_operation_key"),)

    actor_id: Mapped[UUID] = mapped_column(nullable=False)
    operation: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=IdempotencyState.STARTED, nullable=False)
    response_status: Mapped[int | None] = mapped_column(nullable=True)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdempotencyConflict(DomainError):
    code = "idempotency_key_conflict"
    status_code = 409


def canonical_request_hash(payload: object) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def start_or_replay(
    record: IdempotencyRecord | None, request_hash: str
) -> dict[str, object] | None:
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise IdempotencyConflict("Idempotency-Key was previously used with another request")
    if record.state == IdempotencyState.COMPLETED and record.response_body is not None:
        return record.response_body
    raise DomainError("Request with this Idempotency-Key is already in progress")


def complete(
    record: IdempotencyRecord, *, status: int, body: dict[str, object], completed_at: datetime
) -> None:
    record.state = IdempotencyState.COMPLETED
    record.response_status = status
    record.response_body = body
    record.completed_at = completed_at
