from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.routes.strategies import DraftInput, create_draft, list_strategies
from apps.worker.app.tasks import strategies as tasks
from modules.backtesting.engine import BacktestCandle
from modules.connections.models import ConnectionProvider
from modules.identity.authorization import Actor, Role
from modules.knowledge import retrieval as knowledge_retrieval
from modules.knowledge.ingestion import build_source_data
from modules.strategies import research_pipeline
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore
from packages.strategy_sdk.schema import StrategySpecification
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


async def test_verified_binding_launches_strategy_agent_for_ready_selection(database, monkeypatch):
    owner, run_id, selections = await seed(database)
    connection_id = uuid4()
    async with database() as session:
        store = ResourceStore(session)
        selection = await store.get("market_selection", selections[0].id, owner)
        binding = await store.create(
            "provider_binding",
            owner,
            {
                "account_id": selection.data["account_id"],
                "lane": selection.data["lane"],
                "capability": "DISCOVERY",
                "authority_purpose": "DISCOVERY",
                "connection_id": str(connection_id),
                "verification_status": "VERIFIED",
            },
        )
        await store.update(
            selection,
            {**selection.data, "connection_binding_id": str(binding.id)},
        )

    async def resolve(*args):
        return SimpleNamespace(
            id=connection_id,
            profile=SimpleNamespace(provider=ConnectionProvider.TWELVE_DATA),
        )

    async def find(*args):
        return None

    monkeypatch.setattr(research_pipeline, "resolve_connection", resolve)
    monkeypatch.setattr(research_pipeline, "find_connection", find)
    sent = []
    monkeypatch.setattr(tasks.generate_strategy_draft, "delay", sent.append)

    queued = await tasks._queue_top_pair_strategies(run_id)

    assert len(queued) == 1
    assert sent == queued
    async with database() as session:
        store = ResourceStore(session)
        market_run = await store.get("research_run", run_id, owner)
        assert market_run.data["strategy_research"][0]["state"] == "QUEUED"
        strategy_run = await store.get("strategy_research_run", UUID(queued[0]), owner)
        assert strategy_run.data["market_selection_id"] == str(selections[0].id)


async def test_latest_context_shows_all_current_pairs_and_rejects_older_selection(
    database, monkeypatch
):
    owner, old_run_id, old_selections = await seed(database)

    async def find(*args):
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(research_pipeline, "find_connection", find)
    monkeypatch.setattr("apps.api.app.routes.strategies._dispatch_generation", lambda *_: None)
    actor = Actor(uuid4(), owner, Role.OWNER)
    async with database() as session:
        store = ResourceStore(session)
        new_run = await store.create(
            "research_run",
            owner,
            {"account_id": old_selections[0].data["account_id"]},
            state="COMPLETED",
        )
        current = []
        for prior in old_selections:
            current.append(
                await store.create(
                    "market_selection",
                    owner,
                    {**prior.data, "research_run_id": str(new_run.id)},
                    state="ACTIVE_MARKET_ANALYSIS",
                )
            )
        old = await store.get("market_selection", old_selections[0].id, owner)
        await store.update(old, {**old.data, "touched": True})
        context = await research_pipeline.latest_strategy_context(session, owner)
        assert context["market_research_run_id"] == str(new_run.id)
        assert {item["instrument"] for item in context["selections"]} == {"EUR/USD", "BTC-USD"}
        assert all(item["ready"] for item in context["selections"])
        with pytest.raises(HTTPException) as rejected:
            await create_draft(
                DraftInput(origin="AI_GENERATED", market_selection_id=old.id), actor, session
            )
        assert rejected.value.status_code == 409
        draft = await create_draft(
            DraftInput(origin="AI_GENERATED", market_selection_id=current[0].id), actor, session
        )
        assert draft["research_basis"]["market_selection_id"] == str(current[0].id)
        assert draft["research_basis"]["market_research_run_id"] != str(old_run_id)


async def test_degraded_draft_returns_saved_job_evidence(database):
    owner, market_run_id, _ = await seed(database)
    actor = Actor(uuid4(), owner, Role.VIEWER)
    async with database() as session:
        store = ResourceStore(session)
        draft = await store.create(
            "strategy_draft",
            owner,
            {
                "research_basis": {
                    "market_research_run_id": str(market_run_id),
                    "instrument": "EUR/USD",
                }
            },
            state="DEGRADED",
        )
        run = await store.create(
            "strategy_research_run",
            owner,
            {
                "draft_id": str(draft.id),
                "evidence_pack": {"instrument": "EUR/USD"},
                "failure": "TimeoutError",
            },
            state="DEGRADED",
        )
        await store.update(draft, {**draft.data, "research_run_id": str(run.id)})
        result = await list_strategies(actor, session, market_run_id)
        assert len(result) == 1
        assert result[0]["evidence_pack"]["instrument"] == "EUR/USD"
        assert result[0]["failure"] == "TimeoutError"


async def test_validation_failure_records_field_without_echoing_agent_input(database):
    owner, _, _ = await seed(database)
    async with database() as session:
        store = ResourceStore(session)
        draft = await store.create("strategy_draft", owner, {}, state="RESEARCHING")
        run = await store.create(
            "strategy_research_run", owner, {"draft_id": str(draft.id)}, state="RESEARCHING"
        )
    specification = strategy("LONG").model_dump(mode="json")
    specification["risk_per_trade"] = "private agent prose"
    with pytest.raises(ValidationError) as failure:
        StrategySpecification.model_validate(specification)
    await tasks._mark_strategy_research_failed(run.id, failure.value)
    async with database() as session:
        store = ResourceStore(session)
        failed = await store.get("strategy_research_run", run.id, owner)
        degraded_draft = await store.get("strategy_draft", draft.id, owner)
        assert failed.state == "DEGRADED"
        assert failed.data["failure_detail"] == "risk_per_trade: decimal_parsing"
        assert degraded_draft.data["failure_detail"] == failed.data["failure_detail"]
        assert "private agent prose" not in str(failed.data)


async def test_new_cycle_keeps_last_completed_basis_visible(database, monkeypatch):
    owner, completed_run_id, _ = await seed(database)

    async def find(*args):
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(research_pipeline, "find_connection", find)
    async with database() as session:
        await ResourceStore(session).create("research_run", owner, {}, state="QUEUED")
        context = await research_pipeline.latest_strategy_context(session, owner)
        assert context["market_research_run_id"] == str(completed_run_id)
        assert context["newer_market_research_state"] == "QUEUED"
        assert {item["instrument"] for item in context["selections"]} == {"EUR/USD", "BTC-USD"}


@pytest.mark.parametrize("profitable", [True, False])
@pytest.mark.parametrize("cfd", [False, True])
async def test_top_pair_research_persists_levels_or_no_trade(
    database, monkeypatch, profitable, cfd, tmp_path
):
    monkeypatch.setattr(tasks.settings, "research_data_root", tmp_path)
    owner, run_id, selections = await seed(database)
    async with database() as session:
        await ResourceStore(session).create(
            "knowledge_source",
            owner,
            build_source_data(
                name="Reviewed EURUSD trend method",
                content="EUR/USD trending strategy: confirm trend and account for risk and costs.",
                source_kind="YOUTUBE_TRANSCRIPT",
            ),
        )

    async def rerank(session, owner_id, query, hits, limit):
        assert owner_id == owner
        return hits[:limit], {"status": "APPLIED", "provider": "COHERE"}

    monkeypatch.setattr(knowledge_retrieval, "rerank_for_owner", rerank)
    if cfd:
        async with database() as session:
            store = ResourceStore(session)
            for prior in selections:
                item = await store.get("market_selection", prior.id, owner)
                lane = {**item.data["lane"], "instrument_type": "CFD"}
                await store.update(
                    item,
                    {
                        **item.data,
                        "lane": lane,
                        "candidate": {**item.data["candidate"], "lane": lane},
                    },
                )
    connection_id = uuid4()

    async def find(*args):
        return SimpleNamespace(id=connection_id)

    async def resolve(*args):
        return SimpleNamespace(id=connection_id, profile=SimpleNamespace(provider="COINBASE"))

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
            assert role == "strategy_researcher"
            pack = payload["evidence_pack"]
            assert pack["venue_instrument_id"]
            assert pack["specification_version_id"]
            assert "holdout" not in pack
            assert pack["knowledge_retrieval"]["reranking"]["status"] == "APPLIED"
            assert pack["knowledge_retrieval"]["access_mode"] == "BACKEND_RETRIEVAL"
            assert pack["knowledge_context"]
            assert all(hit["authority"] == "CONTEXT_ONLY" for hit in pack["knowledge_context"])
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
    assert result["state"] == (
        "AWAITING_STRATEGY_APPROVAL" if profitable or cfd else "NO_QUALIFYING_STRATEGY"
    )
    assert "trade_setup" not in result
    if profitable or cfd:
        assert result["proposed_specification"]["venue_instrument_id"]
    else:
        assert len(result["preliminary_screen"]["results"]) == 3
    if cfd:
        assert len(result["hypotheses"]) == 17
        assert len({h["specification"]["family"] for h in result["hypotheses"]}) == 7
        assert result["library_candidate_draft_ids"]
        async with database() as session:
            store = ResourceStore(session)
            for candidate_id in result["library_candidate_draft_ids"]:
                alternative = await store.get("strategy_draft", UUID(candidate_id), owner)
                assert alternative.state == "AWAITING_STRATEGY_APPROVAL"
                assert alternative.data["research_basis"]["account_id"]
                assert "trade_setup" not in alternative.data
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


async def test_failed_backtest_unsticks_version_and_records_failed_gates(database):
    owner = uuid4()
    async with database() as session:
        store = ResourceStore(session)
        version = await store.create(
            "strategy_version",
            owner,
            {"latest_backtest_state": "QUEUED", "validation_evidence": {"compiler": True}},
            state="BACKTESTING",
        )
        run = await store.create(
            "strategy_backtest",
            owner,
            {"strategy_version_id": str(version.id)},
            state="QUEUED",
        )
        await store.update(
            version,
            {**version.data, "latest_backtest_id": str(run.id)},
            state="BACKTESTING",
        )
    await tasks._mark_backtest_failed(run.id, TimeoutError())
    async with database() as session:
        store = ResourceStore(session)
        failed = await store.get("strategy_backtest", run.id, owner)
        version = await store.get("strategy_version", version.id, owner)
        assert failed.state == "FAILED"
        assert version.state == "VALIDATING"
        assert version.data["latest_backtest_state"] == "FAILED"
        assert all(
            version.data["validation_evidence"][gate] is False
            for gate in ("backtest", "out_of_sample", "walk_forward", "stress", "policy")
        )


async def test_backtest_recovery_dispatches_queued_and_stale_running(database, monkeypatch):
    owner = uuid4()
    async with database() as session:
        store = ResourceStore(session)
        queued = await store.create("strategy_backtest", owner, {}, state="QUEUED")
        stale = await store.create(
            "strategy_backtest",
            owner,
            {"started_at": (datetime.now(UTC) - timedelta(minutes=21)).isoformat()},
            state="RUNNING",
        )
        fresh = await store.create(
            "strategy_backtest",
            owner,
            {"started_at": datetime.now(UTC).isoformat()},
            state="RUNNING",
        )
    sent = []
    monkeypatch.setattr(tasks.run_strategy_backtest, "delay", sent.append)
    recovered = await tasks._resume_strategy_backtests()
    assert set(recovered) == {str(queued.id), str(stale.id)}
    assert set(sent) == set(recovered)
    assert str(fresh.id) not in recovered
