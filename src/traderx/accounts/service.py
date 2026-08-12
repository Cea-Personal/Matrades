from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from traderx.identity.authorization import Actor, Role, require_role
from traderx.shared.types import as_decimal


@dataclass(frozen=True, slots=True)
class AccountConfiguration:
    id: UUID
    name: str
    currency: str
    starting_balance: Decimal
    version: int = 1


class LiveAccountRegistry:
    """Domain guard used by the persistence service before a live account is enabled."""

    def __init__(self) -> None:
        self._active_live_id: UUID | None = None

    def activate(self, account_id: UUID) -> None:
        if self._active_live_id is not None and self._active_live_id != account_id:
            raise ValueError("only one live trading account may be active")
        self._active_live_id = account_id

    def deactivate(self, account_id: UUID) -> None:
        if self._active_live_id == account_id:
            self._active_live_id = None


def next_version(existing_versions: list[int]) -> int:
    return max(existing_versions, default=0) + 1


def create_account(
    actor: Actor, *, name: str, currency: str, starting_balance: Decimal | str
) -> AccountConfiguration:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "account.create", require_mfa=True)
    amount = as_decimal(starting_balance)
    if amount <= 0:
        raise ValueError("starting balance must be positive")
    if len(currency) != 3:
        raise ValueError("currency must be a three-letter code")
    return AccountConfiguration(uuid4(), name.strip(), currency.upper(), amount)
