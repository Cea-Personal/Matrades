from __future__ import annotations

from uuid import UUID

from modules.credentials.models import ConnectionState, ProviderConnection


class ConnectionService:
    def __init__(self):
        self.items = {}
        self.health_history = []

    def register(self, owner_id: UUID, provider: str, credential_id: UUID) -> ProviderConnection:
        item = ProviderConnection(owner_id=owner_id, provider=provider, credential_id=credential_id)
        self.items[item.id] = item
        return item

    async def test(self, item_id: UUID, check) -> ProviderConnection:
        item = self.items[item_id]
        healthy = await check()
        updated = item.model_copy(
            update={"state": ConnectionState.HEALTHY if healthy else ConnectionState.DEGRADED}
        )
        self.items[item_id] = updated
        self.health_history.append((item_id, updated.state))
        return updated
