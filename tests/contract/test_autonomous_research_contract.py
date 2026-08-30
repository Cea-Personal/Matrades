from uuid import uuid4

from modules.research.matrix import ALL_LANES, normalize_matrix
from packages.contracts.events import LaneLifecyclePayload


def test_all_asset_instrument_lanes_are_typed_and_bounded() -> None:
    assert len(ALL_LANES) == 12
    matrix = normalize_matrix(uuid4())
    assert len(matrix["lanes"]) == 12
    assert {"asset_class", "instrument_type", "status"} <= set(LaneLifecyclePayload.model_fields)
