from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from packages.shared.domain_types import utc_now
from packages.shared.persistence import Base


class OutboxRecord(Base):
    __tablename__ = "outbox_events"
    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    event_type: Mapped[str] = mapped_column(String(160), index=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
