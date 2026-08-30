from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from threading import RLock
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Integer, Numeric, String, Uuid, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from packages.shared.domain_types import utc_now
from packages.shared.persistence import Base


class ReservationState(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    COMMAND_PENDING = "COMMAND_PENDING"
    ORDER_WORKING = "ORDER_WORKING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    OPEN_POSITION = "OPEN_POSITION"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"

    # Compatibility labels for legacy tests and read models. New production
    # writes use the lifecycle states above.
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"


ACTIVE_RESERVATION_STATES = {
    ReservationState.PROVISIONAL.value,
    ReservationState.COMMAND_PENDING.value,
    ReservationState.ORDER_WORKING.value,
    ReservationState.PARTIALLY_FILLED.value,
    ReservationState.OPEN_POSITION.value,
    ReservationState.ACTIVE.value,
    ReservationState.CONFIRMED.value,
}


class PositionRiskReservationRecord(Base):
    """Durable risk capacity claimed by a plan, command, order, or position."""

    __tablename__ = "risk_reservations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    account_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    proposal_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    trade_plan_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True, index=True)
    command_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(160), index=True)
    broker_position_id: Mapped[str | None] = mapped_column(String(160), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), default=ReservationState.PROVISIONAL.value, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PersistentReservationStore:
    """Transaction-scoped reservation authority used by production workflows.

    The account aggregate is locked before capacity is calculated, serializing
    competing plans even when an account has no existing reservation rows.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def reserve(
        self,
        *,
        owner_id: UUID,
        account_id: UUID,
        trade_plan_id: UUID,
        amount: Decimal,
        available: Decimal,
        ttl: timedelta = timedelta(minutes=10),
        details: dict | None = None,
    ) -> PositionRiskReservationRecord:
        from packages.shared.store import ResourceRecord

        account = await self.session.scalar(
            select(ResourceRecord)
            .where(
                ResourceRecord.id == account_id,
                ResourceRecord.owner_id == owner_id,
                ResourceRecord.kind == "account",
                ResourceRecord.state != "DELETED",
            )
            .with_for_update()
        )
        if account is None:
            raise ValueError("active account is required before reserving risk")
        existing = await self.session.scalar(
            select(PositionRiskReservationRecord).where(
                PositionRiskReservationRecord.owner_id == owner_id,
                PositionRiskReservationRecord.trade_plan_id == trade_plan_id,
            )
        )
        if existing is not None:
            if existing.amount != amount:
                raise ValueError("trade plan is already bound to a different risk amount")
            return existing
        await self.expire(account_id=account_id)
        reserved = await self.session.scalar(
            select(func.coalesce(func.sum(PositionRiskReservationRecord.amount), 0)).where(
                PositionRiskReservationRecord.owner_id == owner_id,
                PositionRiskReservationRecord.account_id == account_id,
                PositionRiskReservationRecord.state.in_(ACTIVE_RESERVATION_STATES),
            )
        )
        used = Decimal(str(reserved or 0))
        if amount <= 0 or used + amount > available:
            raise ValueError("insufficient unreserved risk capacity")
        record = PositionRiskReservationRecord(
            owner_id=owner_id,
            account_id=account_id,
            trade_plan_id=trade_plan_id,
            amount=amount,
            state=ReservationState.PROVISIONAL.value,
            expires_at=utc_now() + ttl,
            details=details or {},
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_active(
        self, reservation_id: UUID, *, owner_id: UUID, account_id: UUID
    ) -> PositionRiskReservationRecord | None:
        await self.expire(account_id=account_id)
        return await self.session.scalar(
            select(PositionRiskReservationRecord).where(
                PositionRiskReservationRecord.id == reservation_id,
                PositionRiskReservationRecord.owner_id == owner_id,
                PositionRiskReservationRecord.account_id == account_id,
                PositionRiskReservationRecord.state.in_(ACTIVE_RESERVATION_STATES),
            )
        )

    async def transition(
        self,
        reservation_id: UUID,
        *,
        owner_id: UUID,
        target: ReservationState,
        command_id: UUID | None = None,
        broker_order_id: str | None = None,
        broker_position_id: str | None = None,
        amount: Decimal | None = None,
        reason: str | None = None,
    ) -> PositionRiskReservationRecord:
        record = await self.session.scalar(
            select(PositionRiskReservationRecord)
            .where(
                PositionRiskReservationRecord.id == reservation_id,
                PositionRiskReservationRecord.owner_id == owner_id,
            )
            .with_for_update()
        )
        if record is None:
            raise LookupError("risk reservation not found")
        if record.state in {ReservationState.RELEASED.value, ReservationState.EXPIRED.value}:
            raise ValueError("risk reservation is already terminal")
        record.state = target.value
        record.command_id = command_id or record.command_id
        record.broker_order_id = broker_order_id or record.broker_order_id
        record.broker_position_id = broker_position_id or record.broker_position_id
        if amount is not None:
            if amount < 0 or amount > record.amount:
                raise ValueError("reservation transition amount is invalid")
            record.amount = amount
        record.details = {**record.details, **({"reason": reason} if reason else {})}
        record.version += 1
        record.updated_at = utc_now()
        await self.session.flush()
        return record

    async def split_partial_fill(
        self,
        reservation_id: UUID,
        *,
        owner_id: UUID,
        filled_amount: Decimal,
        broker_position_id: str,
        remaining_command_amount: Decimal,
    ) -> tuple[PositionRiskReservationRecord, PositionRiskReservationRecord | None]:
        record = await self.transition(
            reservation_id,
            owner_id=owner_id,
            target=ReservationState.PARTIALLY_FILLED,
            broker_position_id=broker_position_id,
            amount=filled_amount,
        )
        remainder = None
        if remaining_command_amount > 0:
            remainder = PositionRiskReservationRecord(
                owner_id=record.owner_id,
                account_id=record.account_id,
                trade_plan_id=None,
                command_id=record.command_id,
                amount=remaining_command_amount,
                state=ReservationState.COMMAND_PENDING.value,
                expires_at=record.expires_at,
                details={"split_from": str(record.id)},
            )
            self.session.add(remainder)
            await self.session.flush()
        return record, remainder

    async def expire(self, *, account_id: UUID | None = None) -> int:
        criteria = [
            PositionRiskReservationRecord.state.in_(ACTIVE_RESERVATION_STATES),
            PositionRiskReservationRecord.expires_at <= utc_now(),
        ]
        if account_id is not None:
            criteria.append(PositionRiskReservationRecord.account_id == account_id)
        result = await self.session.execute(
            update(PositionRiskReservationRecord)
            .where(*criteria)
            .values(
                state=ReservationState.EXPIRED.value,
                version=PositionRiskReservationRecord.version + 1,
                updated_at=utc_now(),
            )
        )
        return int(result.rowcount or 0)


@dataclass(frozen=True)
class RiskReservation:
    id: UUID
    account_id: UUID
    proposal_id: UUID
    amount: Decimal
    expires_at: datetime
    state: ReservationState = ReservationState.ACTIVE


class ReservationBook:
    """In-memory compatibility helper for isolated arithmetic tests only."""
    def __init__(self) -> None:
        self._items: dict[UUID, RiskReservation] = {}
        self._lock = RLock()

    def reserve(
        self,
        account_id: UUID,
        proposal_id: UUID,
        amount: Decimal,
        available: Decimal,
        ttl: timedelta = timedelta(minutes=10),
    ) -> RiskReservation:
        with self._lock:
            self.expire()
            already = sum(
                (
                    item.amount
                    for item in self._items.values()
                    if item.account_id == account_id and item.state == ReservationState.ACTIVE
                ),
                Decimal("0"),
            )
            if amount <= 0 or already + amount > available:
                raise ValueError("insufficient unreserved risk capacity")
            item = RiskReservation(uuid4(), account_id, proposal_id, amount, utc_now() + ttl)
            self._items[item.id] = item
            return item

    def transition(self, reservation_id: UUID, state: ReservationState) -> RiskReservation:
        with self._lock:
            current = self._items[reservation_id]
            if current.state != ReservationState.ACTIVE:
                raise ValueError("reservation is no longer active")
            updated = replace(current, state=state)
            self._items[reservation_id] = updated
            return updated

    def active_for(self, reservation_id: UUID, account_id: UUID) -> RiskReservation | None:
        """Return a current reservation only when it is still usable for the account."""
        with self._lock:
            self.expire()
            item = self._items.get(reservation_id)
            if (
                item is None
                or item.account_id != account_id
                or item.state != ReservationState.ACTIVE
            ):
                return None
            return item

    def expire(self) -> None:
        now = utc_now()
        for key, item in tuple(self._items.items()):
            if item.state == ReservationState.ACTIVE and item.expires_at <= now:
                self._items[key] = replace(item, state=ReservationState.EXPIRED)
