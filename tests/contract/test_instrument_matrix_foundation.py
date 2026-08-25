from datetime import UTC, datetime
from uuid import uuid4

import pytest

from modules.market_data.instruments import InstrumentRegistry
from modules.market_data.models import InstrumentSpecificationVersion
from modules.research.matrix import ALL_LANES
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit
from packages.shared.persistence import validate_executable_reference
from tests.fixtures.instrument_matrix import listing, specification, underlying


def test_matrix_has_one_lane_for_each_asset_class_and_instrument_type():
    assert len(ALL_LANES) == 12
    assert {(lane.asset_class, lane.instrument_type) for lane in ALL_LANES} == {
        (asset_class, instrument_type)
        for asset_class in AssetClass
        for instrument_type in InstrumentType
    }


def test_registry_rejects_unknown_listing_and_requires_effective_terms():
    registry = InstrumentRegistry()
    item = listing()
    with pytest.raises(ValueError, match="unknown underlying"):
        registry.register_listing(item)
    registry.register_underlying(underlying())
    registry.register_listing(item)
    with pytest.raises(ValueError, match="provenance"):
        registry.register_specification(
            InstrumentSpecificationVersion(
                venue_instrument_id=item.id,
                effective_from=datetime.now(UTC),
                price_currency="USD",
                quantity_unit=QuantityUnit.UNITS,
                provenance={},
            )
        )
    registry.register_specification(specification(item.id))
    assert registry.specification_at(item.id, datetime.now(UTC)).venue_instrument_id == item.id


def test_executable_typed_writes_cannot_fabricate_terms_or_futures_contract():
    with pytest.raises(ValueError, match="specification"):
        validate_executable_reference(
            {"instrument_type": "SPOT", "venue_instrument_id": str(uuid4())}
        )
    with pytest.raises(ValueError, match="dated futures"):
        validate_executable_reference(
            {
                "instrument_type": "FUTURES",
                "venue_instrument_id": str(uuid4()),
                "specification_version_id": str(uuid4()),
                "quantity_unit": "CONTRACTS",
            }
        )
