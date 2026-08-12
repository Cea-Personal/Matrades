from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


def _integrity_hash(values: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


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
