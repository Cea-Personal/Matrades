from uuid import uuid4

from modules.connections.models import ResearchLaneKey
from modules.research.matrix import missing_binding, new_run
from packages.shared.domain_types import AssetClass, InstrumentType


def test_missing_provider_binding_is_truthful_no_trade() -> None:
    lane = ResearchLaneKey(asset_class=AssetClass.FOREX, instrument_type=InstrumentType.SPOT)
    run = new_run(uuid4(), uuid4(), {"version": 1, "lanes": [lane.model_dump(mode="json")]})
    result = missing_binding(run.id, lane, [])
    assert result.status.value == "NOT_CONFIGURED"
