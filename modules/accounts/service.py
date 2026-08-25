from decimal import Decimal
from uuid import UUID

from modules.accounts.models import AccountSnapshot, TradingAccount


class AccountService:
    def __init__(self) -> None:
        self.items = {}
        self.snapshots: dict[UUID, AccountSnapshot] = {}

    def create(self, item: TradingAccount):
        self.items[item.id] = item
        return item

    def for_owner(self, owner_id: UUID):
        return [x for x in self.items.values() if x.owner_id == owner_id]

    def update(self, owner_id: UUID, item: TradingAccount):
        if item.owner_id != owner_id:
            raise PermissionError
        self.items[item.id] = item
        return item

    def record_snapshot(self, owner_id: UUID, snapshot: AccountSnapshot) -> AccountSnapshot:
        account = self.items.get(snapshot.account_id)
        if account is None or account.owner_id != owner_id:
            raise PermissionError("account does not belong to owner")
        if snapshot.account_id != account.id:
            raise ValueError("snapshot account mismatch")
        self.snapshots[snapshot.account_id] = snapshot
        return snapshot

    def tradable_cash(self, owner_id: UUID, account_id: UUID, currency: str) -> Decimal:
        account = self.items.get(account_id)
        if account is None or account.owner_id != owner_id:
            raise PermissionError("account does not belong to owner")
        # Cash is intentionally separate from derivative margin/position risk.
        snapshot = self.snapshots.get(account_id)
        return snapshot.cash_balances.get(currency, Decimal("0")) if snapshot else Decimal("0")
