from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.routes import strategies as routes
from apps.worker.app.tasks import strategy_monitoring as worker
from modules.identity.authorization import Actor, Role
from modules.strategies.compiler import compile_strategy
from modules.strategies.monitoring import ENGINE, VALIDATION_GATES
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore
from tests.unit.test_forward_monitoring import BASE, bars
from tests.unit.test_strategy_trade_setup import strategy


@pytest.fixture
async def database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def uow():
        async with factory() as session, session.begin():
            yield session

    monkeypatch.setattr(worker, "unit_of_work", uow)
    yield uow
    await engine.dispose()


async def seed(database, state="PAPER_TRADING", **overrides):
    actor = Actor(actor_id=uuid4(), owner_id=uuid4(), role=Role.OWNER)
    spec = strategy(asset_class="CRYPTOCURRENCY")
    artifact = compile_strategy(spec).artifact_hash
    async with database() as db:
        store = ResourceStore(db)
        version = await store.create(
            "strategy_version",
            actor.owner_id,
            {
                "specification": spec.model_dump(mode="json"),
                "artifact_hash": artifact,
                "validation_evidence": dict.fromkeys(VALIDATION_GATES, True),
            },
            state=state,
        )
        run = await store.create(
            "strategy_paper_run",
            actor.owner_id,
            {
                "strategy_version_id": str(version.id),
                "engine": ENGINE,
                "artifact_hash": artifact,
                "timeframe": "1h",
                "trade_count": 10,
                "net_profit": "100",
                "gross_profit": "200",
                "gross_loss": "100",
                "policy_passed": True,
                "data_complete": True,
                "open_positions": [],
                "pending_entries": [],
                "entry_cutoff": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                **overrides,
            },
            state="RUNNING",
        )
        await store.update(version, {**version.data, "paper_run_id": str(run.id)})
    return actor, version.id, run.id


async def test_recorded_paper_review_then_explicit_activation_and_suspend(database):
    actor, version_id, run_id = await seed(database)
    async with database() as db:
        result = await routes.complete_paper_trading(
            version_id, run_id, routes.PaperEvidenceInput(), actor, db
        )
        assert result["strategy"]["state"] == "APPROVED"
        assert all(result["gates"].values())
        with pytest.raises(HTTPException, match="Activate"):
            await routes.create_approved_trade_plan(version_id, routes.TradePlanInput(), actor, db)
        activated = await routes.promote(version_id, actor, db)
        assert activated["state"] == "ACTIVE"
        assert activated["latest_signal"] is None
        suspended = await routes.transition_strategy(
            version_id, routes.TransitionInput(target="SUSPENDED"), actor, db
        )
        assert suspended["state"] == "SUSPENDED"
    assert await worker._evaluate(version_id) == {"status": "INACTIVE_OR_BUSY"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"engine": "manual"},
        {"open_positions": [{"entry": "100"}]},
        {"pending_entries": ["pending"]},
        {"artifact_hash": "changed"},
        {"failure": "Missing provider"},
    ],
)
async def test_invalid_paper_evidence_cannot_approve(database, overrides):
    actor, version_id, run_id = await seed(database, **overrides)
    async with database() as db:
        with pytest.raises(HTTPException) as error:
            await routes.complete_paper_trading(
                version_id, run_id, routes.PaperEvidenceInput(), actor, db
            )
        assert error.value.status_code == 409
        version = await ResourceStore(db).get("strategy_version", version_id, actor.owner_id)
        assert version.state == "PAPER_TRADING"


async def test_failed_observation_gate_returns_to_validation_for_clean_retry(database):
    actor, version_id, run_id = await seed(database, data_complete=False)
    async with database() as db:
        result = await routes.complete_paper_trading(
            version_id, run_id, routes.PaperEvidenceInput(), actor, db
        )
        assert result["strategy"]["state"] == "VALIDATING"
        assert result["strategy"]["validation_evidence"]["paper_forward"] is False


async def test_paper_review_requires_entries_to_be_stopped_or_window_complete(database):
    actor, version_id, run_id = await seed(
        database, entry_cutoff=(datetime.now(UTC) + timedelta(days=1)).isoformat()
    )
    async with database() as db:
        with pytest.raises(HTTPException, match="Stop new paper entries") as error:
            await routes.complete_paper_trading(
                version_id, run_id, routes.PaperEvidenceInput(), actor, db
            )
        assert error.value.status_code == 409


async def test_worker_blocks_legacy_paper_approval_before_fetching_prices(database):
    actor, version_id, _ = await seed(database, state="ACTIVE")
    result = await worker._evaluate(version_id)
    assert result["status"] == "BLOCKED"
    assert "forward paper evidence" in result["reason"]
    async with database() as db:
        version = await ResourceStore(db).get("strategy_version", version_id, actor.owner_id)
        assert version.data["latest_signal"]["entry"] is None


async def test_scheduler_only_dispatches_paper_and_active_versions(database, monkeypatch):
    _, paper_id, _ = await seed(database)
    _, active_id, _ = await seed(database, state="ACTIVE")
    await seed(database, state="APPROVED")
    await seed(database, state="SUSPENDED")
    sent = []
    monkeypatch.setattr(worker.evaluate_strategy, "delay", sent.append)
    assert set(await worker._schedule()) == {str(paper_id), str(active_id)}
    assert set(sent) == {str(paper_id), str(active_id)}


async def test_live_worker_persists_current_signal_and_reuses_cached_history(database, monkeypatch):
    actor, version_id, _ = await seed(database, state="ACTIVE")
    now = BASE.replace(hour=6, second=1)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=UTC):
            return now

    monkeypatch.setattr(worker, "datetime", Clock)
    account_id = uuid4()
    calls = []

    async def resolve(db, owner, version):
        assert owner == actor.owner_id
        return {
            "instrument": "BTC-USD",
            "account_id": str(account_id),
            "historical_timeframe": "1h",
        }, object()

    async def history(*args, **kwargs):
        assert kwargs["account_id"] == account_id
        calls.append(1)
        return bars(6), {"provider": "test"}

    monkeypatch.setattr(worker, "resolve_backtest_basis", resolve)
    monkeypatch.setattr(worker, "historical_candles", history)
    async with database() as db:
        store = ResourceStore(db)
        version = await store.get("strategy_version", version_id, actor.owner_id)
        await store.update(
            version,
            {
                **version.data,
                "validation_evidence": {
                    **version.data["validation_evidence"],
                    "paper": True,
                    "paper_forward": True,
                },
            },
        )
    assert (await worker._evaluate(version_id))["status"] == "SIGNAL"
    assert (await worker._evaluate(version_id))["status"] == "SIGNAL"
    assert len(calls) == 1
    async with database() as db:
        store = ResourceStore(db)
        version = await store.get("strategy_version", version_id, actor.owner_id)
        assert version.data["latest_signal"]["mode"] == "LIVE"
        assert version.data["latest_signal"]["artifact_hash"] == version.data["artifact_hash"]
        assert len(await store.list("strategy_monitor", actor.owner_id)) == 1
        assert await store.list("trade_plan", actor.owner_id) == []


async def test_start_paper_is_idempotent_and_dispatches_first_observation(database, monkeypatch):
    actor = Actor(actor_id=uuid4(), owner_id=uuid4(), role=Role.OWNER)
    spec = strategy(asset_class="CRYPTOCURRENCY")
    artifact = compile_strategy(spec).artifact_hash
    account_id = uuid4()
    async with database() as db:
        store = ResourceStore(db)
        version = await store.create(
            "strategy_version",
            actor.owner_id,
            {
                "specification": spec.model_dump(mode="json"),
                "artifact_hash": artifact,
                "validation_evidence": dict.fromkeys(VALIDATION_GATES, True),
            },
            state="VALIDATING",
        )
        backtest = await store.create(
            "strategy_backtest",
            actor.owner_id,
            {
                "strategy_version_id": str(version.id),
                "artifact_hash": artifact,
                "timeframe": "1h",
                "initial_equity": "10000",
                "spread": "0",
                "commission": "0",
                "slippage": "0",
                "max_daily_loss": "500",
                "max_total_loss": "1000",
            },
            state="PASSED",
        )
        await store.update(version, {**version.data, "latest_backtest_id": str(backtest.id)})

    async def resolve(*_args):
        return {
            "account_id": str(account_id),
            "instrument": "BTC-USD",
            "tick_size": "0.01",
        }, object()

    sent = []
    monkeypatch.setattr(routes, "resolve_backtest_basis", resolve)
    monkeypatch.setattr(
        routes.evaluate_strategy,
        "apply_async",
        lambda *, args, countdown: sent.append((args, countdown)),
    )
    async with database() as db:
        first = await routes.start_paper_trading(
            version.id, routes.PaperTradingInput(duration_days=7), actor, db
        )
    async with database() as db:
        repeated = await routes.start_paper_trading(
            version.id, routes.PaperTradingInput(duration_days=7), actor, db
        )
    assert repeated["id"] == first["id"]
    assert sent == [([str(version.id)], 1)]


async def test_live_shadow_loss_window_automatically_suspends_without_orders(database, monkeypatch):
    actor, version_id, _ = await seed(database, state="ACTIVE")
    values = bars(66)
    for index in range(3, 63, 2):
        values[index] = values[index].model_copy(update={"low": Decimal(80)})
    now = BASE + timedelta(hours=66, seconds=1)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=UTC):
            return now

    async def resolve(*_):
        return {
            "instrument": "EUR/USD",
            "account_id": str(uuid4()),
            "historical_timeframe": "1h",
        }, object()

    async def history(*args, **kwargs):
        return values, {"provider": "test"}

    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(worker, "resolve_backtest_basis", resolve)
    monkeypatch.setattr(worker, "historical_candles", history)
    async with database() as db:
        store = ResourceStore(db)
        version = await store.get("strategy_version", version_id, actor.owner_id)
        await store.update(
            version,
            {
                **version.data,
                "validation_evidence": {
                    **version.data["validation_evidence"],
                    "paper": True,
                    "paper_forward": True,
                },
            },
        )
        await store.create(
            "strategy_monitor",
            actor.owner_id,
            {
                "strategy_version_id": str(version_id),
                "artifact_hash": version.data["artifact_hash"],
                "started_at": (BASE + timedelta(hours=2)).isoformat(),
                "candles": [c.model_dump(mode="json") for c in values],
                "entry_intents": {
                    values[i].observed_at.isoformat(): {
                        "observed_at": values[i].observed_at.isoformat()
                    }
                    for i in range(2, 62, 2)
                },
            },
            record_id=uuid5(NAMESPACE_URL, f"strategy-monitor:{version_id}"),
        )
    assert (await worker._evaluate(version_id))["status"] == "SUSPENDED"
    async with database() as db:
        store = ResourceStore(db)
        version = await store.get("strategy_version", version_id, actor.owner_id)
        assert version.state == "SUSPENDED"
        assert version.data["strategy_health"]["windows"]["30"]["complete"]
        assert version.data["latest_signal"]["entry"] is None
        assert await store.list("trade_plan", actor.owner_id) == []
        with pytest.raises(HTTPException, match="lost its recent edge"):
            await routes.promote(version_id, actor, db)


async def test_library_is_owner_scoped(database):
    actor, version_id, _ = await seed(database)
    other, _, _ = await seed(database)
    async with database() as db:
        store = ResourceStore(db)
        await store.create(
            "strategy_performance",
            other.owner_id,
            {"strategy_version_id": str(version_id), "metrics": {"net_profit": "9999"}},
        )
        records = await routes.list_strategy_library(actor, db)
    assert [r["strategy_version_id"] for r in records] == [str(version_id)]
    assert records[0]["metrics"] == {}
