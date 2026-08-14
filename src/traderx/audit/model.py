from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, String, event
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


def _integrity_hash(values: dict[str, object]) -> str:
    def canonical(value: object) -> str:
        if isinstance(value, datetime):
            aware = value if value.tzinfo else value.replace(tzinfo=UTC)
            return aware.astimezone(UTC).isoformat()
        return str(value)

    return hashlib.sha256(json.dumps(values, sort_keys=True, default=canonical).encode()).hexdigest()


class AuditEvent(IdentifiedMixin, Base):
    __tablename__ = "audit_events"

    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(nullable=True)
    target_version: Mapped[int | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assurance: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    previous_value: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    @classmethod
    def create(cls, **kwargs: object) -> AuditEvent:
        hashed = _integrity_hash(kwargs)
        return cls(integrity_hash=hashed, **kwargs)  # type: ignore[arg-type]

    def verify_integrity(self) -> bool:
        values = {
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "action": self.action,
            "outcome": self.outcome,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_version": self.target_version,
            "reason": self.reason,
            "assurance": self.assurance,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "idempotency_key": self.idempotency_key,
            "previous_value": self.previous_value,
            "new_value": self.new_value,
            "occurred_at": self.occurred_at,
        }
        return self.integrity_hash == _integrity_hash(values)


@event.listens_for(AuditEvent, "before_update")
def _reject_audit_update(*_: object) -> None:
    raise ValueError("audit events are append-only")


@event.listens_for(AuditEvent, "before_delete")
def _reject_audit_delete(*_: object) -> None:
    raise ValueError("audit events are append-only")
