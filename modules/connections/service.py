from __future__ import annotations

from uuid import UUID

from modules.connections.models import MarketDataCapability, ProviderBinding
from modules.credentials.models import ConnectionState, ProviderConnection


class ConnectionService:
    def __init__(self):
        self.items = {}
        self.health_history = []
        self.bindings: dict[UUID, ProviderBinding] = {}

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

    def add_binding(self, binding: ProviderBinding) -> ProviderBinding:
        """Store an immutable, account/lane-scoped provider binding."""
        if binding.connection_id not in self.items:
            raise ValueError("binding references an unknown connection")
        self.bindings[binding.id] = binding
        return binding

    def verify_binding(
        self, binding_id: UUID, *, capabilities: set[MarketDataCapability]
    ) -> ProviderBinding:
        binding = self.bindings[binding_id]
        if binding.capability not in capabilities:
            raise ValueError("connection does not advertise the requested capability")
        updated = binding.model_copy(update={"verification_status": "VERIFIED"})
        self.bindings[binding_id] = updated
        return updated

    def bindings_for(self, account_id: UUID, lane: str) -> list[ProviderBinding]:
        return [
            item
            for item in self.bindings.values()
            if item.account_id == account_id and item.lane.as_string() == lane
        ]

    def remove_binding(self, binding_id: UUID) -> None:
        self.bindings.pop(binding_id, None)
