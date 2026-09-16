from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.worker.app.tasks import strategies as tasks
from modules.backtesting.engine import BacktestCandle
from modules.connections.models import ConnectionProvider
from modules.strategies import research_pipeline
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore
from tests.unit.test_strategy_trade_setup import strategy


@pytest.fixture
async def database(monkeypatch, tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def uow():
        async with factory() as session, session.begin():
            yield session

    monkeypatch.setattr(tasks, "unit_of_work", uow)
    monkeypatch.setattr(tasks.settings, "research_artifact_root", tmp_path)
    yield uow
    await engine.dispose()


async def seed(uow):
    owner = uuid4()
    now = datetime.now(UTC)
    async with uow() as session:
        store = ResourceStore(session)
        account = await store.create("account", owner, {"starting_balance": "10000"})
        run = await store.create(
            "research_run", owner, {"account_id": str(account.id)}, state="COMPLETED"
        )
        selections = []
        for symbol, asset, source in [
            ("EUR/USD", "FOREX", "twelve_data"),
            ("BTC-USD", "CRYPTOCURRENCY", "coinbase_exchange"),
        ]:
            candidate = {
                "lane": {"asset_class": asset, "instrument_type": "SPOT"},
                "listing": {"id": str(uuid4()), "symbol": symbol, "provider": source},
                "specification": {
                    "id": str(uuid4()),
                    "quantity_unit": "UNITS",
                    "tick_size": "0.01",
                },
                "fingerprint": {
                    "observed_at": now.isoformat(),
                    "regime": "TRENDING",
                    "source_cut_id": "history-cut",
                    "data_quality": 1,
                },
                "score": 85,
            }
            selections.append(
                await store.create(
                    "market_selection",
                    owner,
                    {
                        "research_run_id": str(run.id),
                        "account_id": str(account.id),
                        "state": "ACTIVE_MARKET_ANALYSIS",
                        "candidate": candidate,
                        "lane": candidate["lane"],
                    },
                    state="ACTIVE_MARKET_ANALYSIS",
                )
            )
    return owner, run.id, selections


async def test_each_pair_is_pinned_once_and_one_missing_provider_does_not_block_others(
    database,
    monkeypatch,
):
    owner, run_id, selections = await seed(database)
    connection_id = uuid4()

    async def find(db, owner_id, provider):
        assert owner_id == owner
        if provider == ConnectionProvider.COINBASE:
            return None
        return SimpleNamespace(id=connection_id)

    monkeypatch.setattr(research_pipeline, "find_connection", find)
    sent = []
    monkeypatch.setattr(tasks.generate_strategy_draft, "delay", sent.append)
    first = await tasks._queue_top_pair_strategies(run_id)
    assert len(first) == 1
    assert await tasks._queue_top_pair_strategies(run_id) == first
    async with database() as session:
        store = ResourceStore(session)
        drafts = await store.list("strategy_draft", owner)
        assert len(drafts) == 1
        assert drafts[0].data["research_basis"]["market_selection_id"] == str(selections[0].id)
        parent = await store.get("research_run", run_id, owner)
        assert {item["state"] for item in parent.data["strategy_research"]} == {"QUEUED", "BLOCKED"}
        assert await store.list("strategy_draft", uuid4()) == []
        job = await store.get("strategy_research_run", UUID(first[0]), owner)
        await store.update(
            job,
            {**job.data, "started_at": (datetime.now(UTC) - timedelta(minutes=16)).isoformat()},
            state="RESEARCHING",
        )
    assert await tasks._queue_top_pair_strategies(run_id) == first


@pytest.mark.parametrize("profitable", [True, False])
async def test_top_pair_research_persists_levels_or_no_trade(database, monkeypatch, profitable):
    owner, run_id, _ = await seed(database)
    connection_id = uuid4()

    async def find(*args):
        return SimpleNamespace(id=connection_id)

    async def resolve(*args):
        return SimpleNamespace(id=connection_id)

    async def history(connection, instrument, start, end, timeframe, **kwargs):
        return [
            BacktestCandle(
                observed_at=end - timedelta(hours=4 * (100 - index)),
                open=Decimal(100 + index),
                high=Decimal(102 + index),
                low=Decimal(99 + index),
                close=Decimal(101 + index),
                volume=Decimal(1000),
            )
            for index in range(100)
        ], {"provider": "fixture", "source_version": "v1"}

    class Agent:
        def __init__(self, *args):
            pass

        async def invoke(self, role, payload, schema):
            pack = payload["evidence_pack"]
            assert pack["venue_instrument_id"]
            assert pack["specification_version_id"]
            assert "holdout" not in pack
            spec = strategy("LONG" if profitable else "SHORT").model_dump(mode="json")
            spec["instruments"] = [pack["instrument"]]
            return {
                "hypotheses": [
                    {
                        "hypothesis_id": f"H{index}",
                        "strategy": spec,
                        "rationale": "Evidence-based directional strategy",
                        "breakdown": ["Check trend", "Enter next bar", "Apply price protection"],
                        "evidence_refs": [pack["references"][0]["id"]],
                    }
                    for index in range(3)
                ]
            }

        async def close(self):
            pass

    monkeypatch.setattr(research_pipeline, "find_connection", find)
    monkeypatch.setattr(tasks, "resolve_connection", resolve)
    monkeypatch.setattr(tasks, "historical_candles", history)
    monkeypatch.setattr(tasks, "RedisAgentGateway", lambda *args: None)
    monkeypatch.setattr(tasks, "OwnerScopedAgentGateway", Agent)
    monkeypatch.setattr(tasks.generate_strategy_draft, "delay", lambda *args: None)
    queued = await tasks._queue_top_pair_strategies(run_id)
    assert len(queued) == 2
    result = await tasks._generate_strategy(UUID(queued[0]))
    assert result["state"] == ("AWAITING_STRATEGY_APPROVAL" if profitable else "NO_TRADE")
    if profitable:
        assert Decimal(result["trade_setup"]["stop_loss"]) < Decimal(result["trade_setup"]["entry"])
        assert len(result["trade_setup"]["take_profits"]) == 2
        assert result["proposed_specification"]["venue_instrument_id"]
    else:
        assert result["trade_setup"]["entry"] is None
        assert len(result["preliminary_screen"]["results"]) == 3
    repeated = await tasks._generate_strategy(UUID(queued[0]))
    assert repeated["state"] == result["state"]


def test_completed_market_task_dispatches_strategy_research(monkeypatch):
    from apps.worker.app.tasks import research

    run_id = uuid4()
    sent = []

    async def complete(parsed):
        assert parsed == run_id
        return {"state": "COMPLETED"}

    monkeypatch.setattr(research, "_execute_research_cycle", complete)
    monkeypatch.setattr(research.queue_top_pair_strategies, "delay", sent.append)
    assert research.run_research_cycle.run(str(run_id)) == {"state": "COMPLETED"}
    assert sent == [str(run_id)]
