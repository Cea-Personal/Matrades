from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.routes import configuration
from apps.api.app.routes import strategies as strategy_routes
from apps.worker.app.tasks import strategy_autonomy
from modules.connections.models import ConnectionProvider
from modules.identity.authorization import Actor, Role
from modules.strategies.autonomy import StrategyAutomationPolicy
from modules.strategies.monitoring import VALIDATION_GATES
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore
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

    monkeypatch.setattr(strategy_autonomy, "unit_of_work", uow)
    monkeypatch.setattr(strategy_autonomy, "session_factory", factory)
    yield factory
    await engine.dispose()


async def account_and_policy(factory, *, enabled=True, attempts=1):
    actor = Actor(uuid4(), uuid4(), Role.OWNER)
    async with factory() as db, db.begin():
        account = await ResourceStore(db).create(
            "account",
            actor.owner_id,
            {
                "name": "Automation account",
                "starting_balance": "10000",
                "strategy_validation_automation": StrategyAutomationPolicy(
                    enabled=enabled, max_paper_attempts=attempts
                ).model_dump(mode="json"),
            },
        )
    return actor, account


async def test_owner_can_enable_bounded_non_executing_strategy_automation(database):
    actor, account = await account_and_policy(database, enabled=False)
    policy = StrategyAutomationPolicy(
        enabled=True,
        backtest_lookback_days=60,
        paper_duration_days=14,
        max_paper_attempts=2,
        spread="0.1",
        slippage="0.05",
    )
    async with database() as db, db.begin():
        saved = await configuration.update_strategy_automation(account.id, policy, actor, db)
    assert saved["enabled"] is True
    assert saved["paper_duration_days"] == 14
    async with database() as db, db.begin():
        loaded = await configuration.get_strategy_automation(account.id, actor, db)
    assert loaded["max_paper_attempts"] == 2


async def test_waiting_history_retries_require_due_time_and_owner_opt_in(database, monkeypatch):
    actor, account = await account_and_policy(database)
    async with database() as db, db.begin():
        store = ResourceStore(db)
        due = await store.create(
            "strategy_version",
            actor.owner_id,
            {
                "research_basis": {
                    "account_id": str(account.id),
                    "instrument": "EUR/USD",
                    "historical_timeframe": "1h",
                },
                "latest_backtest_state": "WAITING_FOR_DATA",
                "validation_retry_after_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            },
            state="VALIDATING",
        )
        future = await store.create(
            "strategy_version",
            actor.owner_id,
            {
                **due.data,
                "validation_retry_after_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
            state="VALIDATING",
        )
    sent = []
    monkeypatch.setattr(strategy_autonomy.retry_strategy_backtest, "delay", sent.append)
    assert await strategy_autonomy._schedule() == [f"backtest-retry:{due.id}"]
    assert sent == [str(due.id)]
    assert await strategy_autonomy._retry_waiting_backtest(future.id) == "WAITING_FOR_DATA"
    # Missing hard risk authority blocks a retry once, rather than repeatedly scheduling it.
    assert await strategy_autonomy._retry_waiting_backtest(due.id) == "BLOCKED"
    assert await strategy_autonomy._schedule() == []
    async with database() as db, db.begin():
        saved = await ResourceStore(db).get("account", account.id, actor.owner_id)
        await ResourceStore(db).update(
            saved, {**saved.data, "strategy_validation_automation": {"enabled": False}}
        )
    assert await strategy_autonomy._retry_waiting_backtest(due.id) == "MANUAL"


async def test_due_history_retry_creates_one_actual_provider_pinned_backtest(database, monkeypatch):
    actor, account = await account_and_policy(database)
    connection_id, binding_id = uuid4(), uuid4()
    async with database() as db, db.begin():
        store = ResourceStore(db)
        version = await store.create(
            "strategy_version",
            actor.owner_id,
            {
                "specification": strategy().model_dump(mode="json"),
                "research_basis": {
                    "account_id": str(account.id),
                    "instrument": "EUR/USD",
                    "historical_timeframe": "1h",
                },
                "latest_backtest_state": "WAITING_FOR_DATA",
                "validation_retry_after_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            },
            state="VALIDATING",
        )
        await store.create(
            "guardrail",
            actor.owner_id,
            {
                "account_id": str(account.id),
                "rules": [
                    {"kind": "MAX_DAILY_LOSS", "value": "500", "enforcement": "HARD"},
                    {"kind": "MAX_TOTAL_DRAWDOWN", "value": "1000", "enforcement": "HARD"},
                ],
            },
            state="ACTIVE",
        )

    async def resolve(*_):
        return {
            "account_id": str(account.id),
            "instrument": "EUR/USD",
            "historical_connection_id": str(connection_id),
            "connection_binding_id": str(binding_id),
            "historical_timeframe": "1h",
        }, SimpleNamespace(profile=SimpleNamespace(provider=ConnectionProvider.TWELVE_DATA))

    monkeypatch.setattr(strategy_routes, "resolve_backtest_basis", resolve)
    sent = []
    monkeypatch.setattr(strategy_routes, "_dispatch_backtest", sent.append)
    assert await strategy_autonomy._retry_waiting_backtest(version.id) == "BACKTESTING"
    assert await strategy_autonomy._retry_waiting_backtest(version.id) == "INACTIVE"
    async with database() as db:
        (run,) = await ResourceStore(db).list("strategy_backtest", actor.owner_id)
        assert run.data["connection_id"] == str(connection_id)
        assert run.data["max_daily_loss"] == "500"
        assert sent == [run.id]


async def test_scheduler_dispatches_only_enabled_eligible_stages(database, monkeypatch):
    actor, account = await account_and_policy(database, attempts=1)
    async with database() as db, db.begin():
        store = ResourceStore(db)
        draft = await store.create(
            "strategy_draft",
            actor.owner_id,
            {"research_basis": {"account_id": str(account.id)}},
            state="AWAITING_STRATEGY_APPROVAL",
        )
        validating = await store.create(
            "strategy_version",
            actor.owner_id,
            {
                "research_basis": {"account_id": str(account.id)},
                "validation_evidence": dict.fromkeys(VALIDATION_GATES, True),
            },
            state="VALIDATING",
        )
        paper = await store.create(
            "strategy_version",
            actor.owner_id,
            {"research_basis": {"account_id": str(account.id)}},
            state="PAPER_TRADING",
        )
        run = await store.create(
            "strategy_paper_run",
            actor.owner_id,
            {
                "strategy_version_id": str(paper.id),
                "entry_cutoff": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "open_positions": [],
                "pending_entries": [],
            },
            state="RUNNING",
        )
        await store.update(paper, {**paper.data, "paper_run_id": str(run.id)})
    drafts, papers, reviews = [], [], []
    monkeypatch.setattr(strategy_autonomy.advance_strategy_draft, "delay", drafts.append)
    monkeypatch.setattr(strategy_autonomy.start_strategy_paper, "delay", papers.append)
    monkeypatch.setattr(
        strategy_autonomy.review_strategy_paper,
        "delay",
        lambda version, run: reviews.append((version, run)),
    )
    actions = await strategy_autonomy._schedule()
    assert drafts == [str(draft.id)]
    assert papers == [str(validating.id)]
    assert reviews == [(str(paper.id), str(run.id))]
    assert len(actions) == 3


async def test_autonomous_draft_uses_owner_policy_and_hard_loss_limits(database, monkeypatch):
    actor, account = await account_and_policy(database)
    draft_id = uuid4()
    async with database() as db, db.begin():
        store = ResourceStore(db)
        await store.create(
            "strategy_draft",
            actor.owner_id,
            {
                "origin": "AI_GENERATED",
                "proposed_specification": strategy().model_dump(mode="json"),
                "research_basis": {
                    "account_id": str(account.id),
                    "instrument": "EUR/USD",
                    "historical_timeframe": "1h",
                },
            },
            state="AWAITING_STRATEGY_APPROVAL",
            record_id=draft_id,
        )
        for kind, value in (("MAX_DAILY_LOSS", "500"), ("MAX_TOTAL_DRAWDOWN", "1000")):
            await store.create(
                "guardrail",
                actor.owner_id,
                {"account_id": str(account.id), "rules": [{"kind": kind, "value": value}]},
                state="ACTIVE",
            )

    async def resolve(db, owner_id, version):
        return {
            "account_id": str(account.id),
            "instrument": "EUR/USD",
            "historical_timeframe": "1h",
            "historical_connection_id": str(uuid4()),
            "connection_binding_id": str(uuid4()),
        }, SimpleNamespace(profile=SimpleNamespace(provider=ConnectionProvider.TWELVE_DATA))

    async def embed(db, owner_id, data):
        return data

    monkeypatch.setattr(strategy_routes, "resolve_backtest_basis", resolve)
    monkeypatch.setattr(strategy_routes, "embed_source_data", embed)
    monkeypatch.setattr(strategy_routes, "_dispatch_backtest", lambda _: None)
    assert await strategy_autonomy._advance_draft(draft_id) == "BACKTESTING"
    async with database() as db:
        store = ResourceStore(db)
        versions = await store.list("strategy_version", actor.owner_id)
        backtests = await store.list("strategy_backtest", actor.owner_id)
        draft = await store.get("strategy_draft", draft_id, actor.owner_id)
        assert len(versions) == len(backtests) == 1
        assert versions[0].state == "BACKTESTING"
        assert versions[0].data["approval_authority"] == "AUTOMATION_POLICY"
        assert draft.data["provenance"]["human_approval"] == "NOT_REQUESTED"
        assert backtests[0].data["max_daily_loss"] == "500"
        assert backtests[0].data["max_total_loss"] == "1000"
        assert await store.list("trade_plan", actor.owner_id) == []
        assert await store.list("execution_command", actor.owner_id) == []


async def test_missing_policy_rolls_back_and_waits_for_new_owner_policy(database, monkeypatch):
    actor, account = await account_and_policy(database)
    async with database() as db, db.begin():
        draft = await ResourceStore(db).create(
            "strategy_draft",
            actor.owner_id,
            {
                "origin": "AI_GENERATED",
                "proposed_specification": strategy().model_dump(mode="json"),
                "research_basis": {"account_id": str(account.id), "instrument": "EUR/USD"},
            },
            state="AWAITING_STRATEGY_APPROVAL",
        )

    async def embed(db, owner_id, data):
        return data

    monkeypatch.setattr(strategy_routes, "embed_source_data", embed)
    assert await strategy_autonomy._advance_draft(draft.id) == "BLOCKED"
    async with database() as db:
        store = ResourceStore(db)
        blocked = await store.get("strategy_draft", draft.id, actor.owner_id)
        assert blocked.state == "AWAITING_STRATEGY_APPROVAL"
        assert "MAX_DAILY_LOSS" in blocked.data["automation_failure"]
        assert await store.list("strategy_version", actor.owner_id) == []
    assert await strategy_autonomy._schedule() == []
