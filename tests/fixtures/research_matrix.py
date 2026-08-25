"""Account matrix and provider-binding fixtures."""

from uuid import UUID

from modules.connections.models import (
    MarketDataCapability,
    ProviderAuthorityPurpose,
    ProviderBinding,
)
from modules.research.matrix import ALL_LANES


def matrix(account_id: UUID) -> dict:
    return {
        "account_id": str(account_id),
        "version": 1,
        "lanes": [lane.model_dump(mode="json") for lane in ALL_LANES],
        "schedule": {
            "enabled": True,
            "run_at": "05:00",
            "timezone": "UTC",
            "weekdays": [0, 1, 2, 3, 4],
        },
    }


def binding(account_id: UUID, connection_id: UUID, lane_index: int = 0) -> ProviderBinding:
    return ProviderBinding(
        account_id=account_id,
        lane=ALL_LANES[lane_index],
        capability=MarketDataCapability.DISCOVERY,
        authority_purpose=ProviderAuthorityPurpose.DISCOVERY,
        connection_id=connection_id,
        priority=1,
        verification_status="VERIFIED",
    )
