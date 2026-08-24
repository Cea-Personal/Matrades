from uuid import UUID

from modules.accounts.models import TradingAccount


class AccountService:
    def __init__(self) -> None:
        self.items = {}

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
