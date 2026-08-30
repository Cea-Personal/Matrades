from types import SimpleNamespace
from uuid import uuid4

from apps.worker.app.tasks.research import _verified_market_bindings


def test_economic_bindings_do_not_enter_typed_market_validation() -> None:
    account_id = str(uuid4())
    connection_id = str(uuid4())
    records = [
        SimpleNamespace(
            data={
                "binding_scope": "ECONOMIC_CONTEXT",
                "account_id": account_id,
                "lane": None,
                "capability": "ECONOMIC_CALENDAR",
                "authority_purpose": "REFERENCE",
                "connection_id": connection_id,
                "verification_status": "VERIFIED",
            }
        ),
        SimpleNamespace(
            data={
                "binding_scope": "MARKET_RESEARCH",
                "account_id": account_id,
                "lane": {"asset_class": "FOREX", "instrument_type": "CFD"},
                "capability": "DISCOVERY",
                "authority_purpose": "DISCOVERY",
                "connection_id": connection_id,
                "verification_status": "VERIFIED",
            }
        ),
    ]

    bindings = _verified_market_bindings(records, account_id)

    assert len(bindings) == 1
    assert bindings[0].lane.as_string() == "FOREX:CFD"
    assert bindings[0].capability.value == "DISCOVERY"


def test_legacy_verified_market_binding_with_a_lane_remains_supported() -> None:
    account_id = str(uuid4())
    records = [
        SimpleNamespace(
            data={
                "account_id": account_id,
                "lane": {"asset_class": "METALS", "instrument_type": "CFD"},
                "capability": "CANDLES",
                "authority_purpose": "HISTORY",
                "connection_id": str(uuid4()),
                "verification_status": "VERIFIED",
            }
        )
    ]

    bindings = _verified_market_bindings(records, account_id)

    assert len(bindings) == 1
    assert bindings[0].lane.as_string() == "METALS:CFD"
