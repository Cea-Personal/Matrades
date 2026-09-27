from types import SimpleNamespace
from uuid import uuid4

import pytest

from modules.backtesting import basis as module
from modules.connections.models import ConnectionProvider


def case(monkeypatch, asset="FOREX", provider=ConnectionProvider.TWELVE_DATA):
    owner, account, selection_id, binding_id, connection_id = [uuid4() for _ in range(5)]
    lane = {"asset_class": asset, "instrument_type": "CFD"}
    selection = SimpleNamespace(
        data={
            "account_id": str(account),
            "lane": lane,
            "connection_binding_id": str(binding_id),
            "candidate": {
                "listing": {"provider": provider.value, "symbol": "TEST"},
                "fingerprint": {"source_cut_id": "mt5:sequence:H1"},
            },
        }
    )
    binding = SimpleNamespace(
        id=binding_id,
        data={
            "account_id": str(account),
            "lane": lane,
            "verification_status": "VERIFIED",
            "connection_id": str(connection_id),
        },
    )
    version = SimpleNamespace(
        data={
            "research_basis": {
                "market_selection_id": str(selection_id),
                "account_id": str(account),
            }
        }
    )
    records = {
        ("market_selection", selection_id): selection,
        ("provider_binding", binding_id): binding,
        ("account", account): SimpleNamespace(state="ACTIVE"),
    }

    class Store:
        def __init__(self, db):
            pass

        async def get(self, kind, record_id, owner_id):
            assert owner_id == owner
            return records.get((kind, record_id))

    async def connection(db, owner_id, record_id):
        assert owner_id == owner and record_id == connection_id
        return SimpleNamespace(id=connection_id, profile=SimpleNamespace(provider=provider))

    monkeypatch.setattr(module, "ResourceStore", Store)
    monkeypatch.setattr(module, "resolve_connection", connection)
    return owner, version, selection, binding, account


@pytest.mark.parametrize(
    "asset,provider",
    [
        ("FOREX", ConnectionProvider.TWELVE_DATA),
        ("FOREX", ConnectionProvider.MT5_BRIDGE),
        ("METALS", ConnectionProvider.MT5_BRIDGE),
        ("CRYPTOCURRENCY", ConnectionProvider.COINBASE),
    ],
)
async def test_expected_provider_is_pinned_to_account(monkeypatch, asset, provider):
    owner, version, _, _, account = case(monkeypatch, asset, provider)
    result, connection = await module.resolve_backtest_basis(None, owner, version)
    assert result["account_id"] == str(account)
    assert result["historical_connection_id"] == str(connection.id)
    assert result["historical_provider"] == provider.value


@pytest.mark.parametrize(
    "asset,provider",
    [
        ("FOREX", ConnectionProvider.COINBASE),
        ("METALS", ConnectionProvider.TWELVE_DATA),
        ("CRYPTOCURRENCY", ConnectionProvider.MT5_BRIDGE),
    ],
)
async def test_wrong_provider_is_rejected(monkeypatch, asset, provider):
    owner, version, *_ = case(monkeypatch, asset, provider)
    with pytest.raises(ValueError, match="cannot backtest"):
        await module.resolve_backtest_basis(None, owner, version)


@pytest.mark.parametrize(
    "field,value", [("account_id", str(uuid4())), ("verification_status", "UNVERIFIED")]
)
async def test_binding_must_remain_verified_for_same_account(monkeypatch, field, value):
    owner, version, _, binding, _ = case(monkeypatch)
    binding.data[field] = value
    with pytest.raises(ValueError, match="no longer verified"):
        await module.resolve_backtest_basis(None, owner, version)
