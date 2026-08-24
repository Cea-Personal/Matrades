from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from threading import RLock
from uuid import UUID, uuid4

from packages.shared.domain_types import utc_now


class ReservationState(StrEnum):
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class RiskReservation:
    id: UUID
    account_id: UUID
    proposal_id: UUID
    amount: Decimal
    expires_at: datetime
    state: ReservationState = ReservationState.ACTIVE


class ReservationBook:
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

    def expire(self) -> None:
        now = utc_now()
        for key, item in tuple(self._items.items()):
            if item.state == ReservationState.ACTIVE and item.expires_at <= now:
                self._items[key] = replace(item, state=ReservationState.EXPIRED)
