from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from apps.api.app.routes import strategies
from modules.connections.models import ConnectionProvider
from modules.identity.authorization import Actor, Role


def setup(monkeypatch, provider=ConnectionProvider.TWELVE_DATA):
    version_id, connection_id, account_id = uuid4(), uuid4(), uuid4()
    actor = Actor(actor_id=uuid4(), owner_id=uuid4(), role=Role.OWNER)
    saved = []
    version = SimpleNamespace(
        state="IMPLEMENTED", data={"specification": {"instruments": ["USD/CAD"]}}
    )
    basis = dict(
        historical_connection_id=str(connection_id),
        account_id=str(account_id),
        instrument="USD/CAD",
        connection_binding_id=str(uuid4()),
        historical_timeframe="1h",
    )

    async def resolve(db, owner, item):
        assert owner == actor.owner_id and item is version
        return basis, SimpleNamespace(profile=SimpleNamespace(provider=provider))

    class Store:
        def __init__(self, db):
            pass

        async def get(self, kind, record_id, owner_id):
            return version

        async def create(self, kind, owner, data, **kwargs):
            saved.append(data)
            return SimpleNamespace(id=uuid4(), public=lambda: data)

        async def update(self, *args, **kwargs):
            pass

    async def commit():
        pass

    async def scalar(_statement):
        return version

    monkeypatch.setattr(strategies, "resolve_backtest_basis", resolve)
    monkeypatch.setattr(strategies, "ResourceStore", Store)
    monkeypatch.setattr(strategies, "_dispatch_backtest", lambda _: None)
    payload = strategies.BacktestInput(
        instrument="USD/CAD",
        start_at=datetime.now(UTC) - timedelta(days=7),
        end_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return version_id, actor, SimpleNamespace(commit=commit, scalar=scalar), payload, saved, basis


async def test_backtest_automatically_pins_connection_account_and_clips_future_end(monkeypatch):
    version, actor, db, payload, saved, basis = setup(monkeypatch)
    await strategies.create_backtest(version, payload, actor, db)
    assert saved[0]["connection_id"] == basis["historical_connection_id"]
    assert saved[0]["account_id"] == basis["account_id"]
    assert datetime.fromisoformat(saved[0]["end_at"]) <= datetime.now(UTC)
    assert saved[0]["requested_end_at"] == payload.end_at.isoformat()


@pytest.mark.parametrize("field,value", [("connection_id", uuid4()), ("instrument", "BTC-USD")])
async def test_backtest_rejects_connection_or_instrument_override(monkeypatch, field, value):
    version, actor, db, payload, saved, _ = setup(monkeypatch)
    payload = payload.model_copy(update={field: value})
    with pytest.raises(HTTPException) as error:
        await strategies.create_backtest(version, payload, actor, db)
    assert error.value.status_code == 422
    assert saved == []


async def test_mt5_backtest_requires_published_timeframe(monkeypatch):
    version, actor, db, payload, saved, _ = setup(monkeypatch, ConnectionProvider.MT5_BRIDGE)
    payload.timeframe = "4h"
    with pytest.raises(HTTPException, match="MT5 published history"):
        await strategies.create_backtest(version, payload, actor, db)
    assert saved == []
