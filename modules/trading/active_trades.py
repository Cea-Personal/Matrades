from uuid import UUID

from modules.trading.broker_models import ActiveTrade
from packages.broker_sdk.schemas import BrokerPosition


def promote_actual(
    owner_id: UUID, proposal_id: UUID, broker_position: BrokerPosition
) -> ActiveTrade:
    return ActiveTrade(owner_id=owner_id, proposal_id=proposal_id, broker_position=broker_position)
