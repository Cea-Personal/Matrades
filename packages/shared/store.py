from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import JSON, DateTime, Integer, String, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from packages.shared.domain_types import utc_now
from packages.shared.persistence import Base, validate_executable_reference


class ResourceRecord(Base):
    """Durable, owner-scoped aggregate storage for versioned application resources."""

    __tablename__ = "resource_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(48), index=True, default="ACTIVE", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    def public(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "owner_id": str(self.owner_id),
            "kind": self.kind,
            "state": self.state,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            **self.data,
        }


class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    event_type: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    aggregate_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, default=uuid4, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    def public(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "owner_id": str(self.owner_id),
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id) if self.aggregate_id else None,
            "correlation_id": str(self.correlation_id),
            "evidence": self.evidence,
            "created_at": self.created_at,
        }


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    owner_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ResourceStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        kind: str,
        owner_id: UUID,
        data: dict[str, Any],
        *,
        state: str = "ACTIVE",
        record_id: UUID | None = None,
        actor_id: UUID | None = None,
        event_type: str | None = None,
    ) -> ResourceRecord:
        validate_executable_reference(data)
        record = ResourceRecord(
            id=record_id or uuid4(),
            owner_id=owner_id,
            kind=kind,
            state=state,
            data=jsonable_encoder(data),
        )
        self.session.add(record)
        await self.session.flush()
        await self.audit(
            owner_id,
            actor_id,
            event_type or f"{kind}.created",
            kind,
            record.id,
            {"state": state, "version": record.version},
        )
        return record

    async def get(self, kind: str, record_id: UUID, owner_id: UUID) -> ResourceRecord | None:
        return await self.session.scalar(
            select(ResourceRecord).where(
                ResourceRecord.id == record_id,
                ResourceRecord.kind == kind,
                ResourceRecord.owner_id == owner_id,
            )
        )

    async def list(
        self, kind: str, owner_id: UUID, *, include_deleted: bool = False
    ) -> list[ResourceRecord]:
        statement = select(ResourceRecord).where(
            ResourceRecord.kind == kind, ResourceRecord.owner_id == owner_id
        )
        if not include_deleted:
            statement = statement.where(ResourceRecord.state != "DELETED")
        statement = statement.order_by(ResourceRecord.updated_at.desc())
        return list((await self.session.scalars(statement)).all())

    async def update(
        self,
        record: ResourceRecord,
        data: dict[str, Any] | None = None,
        *,
        state: str | None = None,
        expected_version: int | None = None,
        actor_id: UUID | None = None,
        event_type: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> ResourceRecord:
        if expected_version is not None and record.version != expected_version:
            raise ValueError("resource version conflict")
        if data is not None:
            validate_executable_reference(data)
            record.data = jsonable_encoder(data)
        if state is not None:
            record.state = state
        record.version += 1
        record.updated_at = utc_now()
        await self.session.flush()
        await self.audit(
            record.owner_id,
            actor_id,
            event_type or f"{record.kind}.updated",
            record.kind,
            record.id,
            evidence or {"state": record.state, "version": record.version},
        )
        return record

    async def audit(
        self,
        owner_id: UUID,
        actor_id: UUID | None,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID | None,
        evidence: dict[str, Any],
    ) -> AuditRecord:
        item = AuditRecord(
            owner_id=owner_id,
            actor_id=actor_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            evidence=jsonable_encoder(evidence),
        )
        self.session.add(item)
        await self.session.flush()
        return item
