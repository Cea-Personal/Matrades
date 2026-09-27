from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.worker.app.tasks import strategies as worker
from modules.strategies.compiler import compile_strategy
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore
from tests.unit.test_pair_strategy_library import history
from tests.unit.test_strategy_trade_setup import strategy


@pytest.mark.parametrize("selection_index", [30, 195])
async def test_formal_backtest_persists_only_oos_regime_mapping(
    monkeypatch, tmp_path, selection_index
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def uow():
        async with factory() as session, session.begin():
            yield session

    monkeypatch.setattr(worker, "unit_of_work", uow)
    monkeypatch.setattr(worker.settings, "research_artifact_root", tmp_path)
    owner_id, account_id, connection_id, selection_id = uuid4(), uuid4(), uuid4(), uuid4()
    spec, values = strategy(), history(200)
    basis = {
        "market_selection_id": str(selection_id),
        "account_id": str(account_id),
        "instrument": "EUR/USD",
        "historical_connection_id": str(connection_id),
        "historical_timeframe": "1m",
    }

    async def resolve(*_):
        return basis, object()

    async def candles(*args, **kwargs):
        assert kwargs["account_id"] == account_id
        return values, {"provider": "test"}

    monkeypatch.setattr(worker, "resolve_backtest_basis", resolve)
    monkeypatch.setattr(worker, "historical_candles", candles)
    async with uow() as db:
        store = ResourceStore(db)
        await store.create(
            "market_selection",
            owner_id,
            {
                "candidate": {
                    "specification": {
                        "tick_size": ".01",
                        "price_currency": "USD",
                        "quantity_step": ".01",
                        "quantity_minimum": ".01",
                        "contract_multiplier": "1",
                    }
                }
            },
            record_id=selection_id,
        )
        version = await store.create(
            "strategy_version",
            owner_id,
            {
                "specification": spec.model_dump(mode="json"),
                "artifact_hash": compile_strategy(spec).artifact_hash,
                "research_selection_cut_at": values[selection_index].observed_at.isoformat(),
            },
            state="BACKTESTING",
        )
        run = await store.create(
            "strategy_backtest",
            owner_id,
            {
                "strategy_version_id": str(version.id),
                "connection_id": str(connection_id),
                "account_id": str(account_id),
                "instrument": "EUR/USD",
                "timeframe": "1m",
                "start_at": values[0].observed_at.isoformat(),
                "end_at": (values[-1].observed_at + timedelta(minutes=1)).isoformat(),
                "initial_equity": "10000",
                "spread": "0.01",
                "commission": "0",
                "slippage": "0.01",
            },
            state="QUEUED",
        )
        await store.update(version, {**version.data, "latest_backtest_id": str(run.id)})
    result = await worker._run_backtest(run.id)
    if selection_index == 195:
        assert result["state"] == "WAITING_FOR_DATA"
        assert result["retry_after_at"]
        assert result["robustness"]["unseen_candle_count"] < 60
        assert not result["gates"]["out_of_sample"]
    async with uow() as db:
        (performance,) = await ResourceStore(db).list("strategy_performance", owner_id)
        assert performance.data["account_id"] == str(account_id)
        assert performance.data["connection_id"] == str(connection_id)
        assert (
            performance.data["regime_performance"]
            == result["robustness"]["out_of_sample"]["regime_performance"]
        )
        assert performance.data["all_history_regime_performance"] == result["regime_performance"]
        assert performance.data["robustness"]["independent_of_research_selection"]
    assert (await worker._run_backtest(run.id))["state"] == result["state"]
    await engine.dispose()
