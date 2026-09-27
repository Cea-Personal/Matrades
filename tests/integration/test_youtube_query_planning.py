from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import current_actor, get_db
from apps.api.app.routes import knowledge
from apps.worker.app.tasks import knowledge as tasks
from modules.identity.authorization import Actor, Role
from modules.knowledge.query_planning import choose_scheduled_query
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


@pytest.fixture
async def workspace():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        store = ResourceStore(db)
        owner = uuid4()
        account = await store.create("account", owner, {})
        run = await store.create(
            "research_run",
            owner,
            {
                "account_id": str(account.id),
            },
            state="COMPLETED",
        )
        run.created_at = NOW - timedelta(days=1)

        async def selection(
            symbol="EUR/USD",
            regime="TRENDING",
            score=90,
            age=0,
            owner_id=owner,
            account_id=account.id,
            research_run=run,
        ):
            lane = {
                "asset_class": "METALS" if symbol.startswith("XAU") else "FOREX",
                "instrument_type": "CFD",
            }
            return await store.create(
                "market_selection",
                owner_id,
                {
                    "account_id": str(account_id),
                    "research_run_id": str(research_run.id),
                    "lane": lane,
                    "candidate": {
                        "listing": {"symbol": symbol},
                        "lane": lane,
                        "score": score,
                        "fingerprint": {
                            "regime": regime,
                            "observed_at": (NOW - timedelta(hours=age)).isoformat(),
                        },
                    },
                },
                state="ACTIVE_MARKET_ANALYSIS",
            )

        async def record(plan):
            return await store.create(
                "youtube_discovery_run",
                owner,
                {
                    "trigger": "SCHEDULED",
                    "query": plan["query"],
                    "query_plan": plan,
                },
                state="SUCCEEDED",
            )

        actor = Actor(uuid4(), owner, Role.OWNER)
        app = FastAPI()
        app.include_router(knowledge.router)

        async def session():
            yield db

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[current_actor] = lambda: actor
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield SimpleNamespace(
                db=db,
                store=store,
                owner=owner,
                account=account,
                run=run,
                selection=selection,
                record=record,
                client=client,
            )
    await engine.dispose()


async def plan(workspace, **schedule):
    return await choose_scheduled_query(
        workspace.db, workspace.owner, {"query_mode": "AUTO_MARKET", **schedule}, now=NOW
    )


async def test_auto_plan_rotates_pairs_before_topics_and_respects_regimes(workspace):
    await workspace.selection("XAUUSDm", "TRENDING:HIGH_VOLATILITY", 95)
    await workspace.selection("EUR/USD", "RANGING:LOW_VOLATILITY", 90)
    first = await plan(workspace)
    assert first["instrument"] == "XAUUSDm" and first["topic"] == "trend"
    assert "gold XAUUSD CFD trending market high volatility" in first["query"]
    await workspace.record(first)
    second = await plan(workspace)
    assert second["instrument"] == "EUR/USD" and second["topic"] == "mean_reversion"
    assert "range bound market low volatility" in second["query"]
    await workspace.record(second)
    third = await plan(workspace)
    assert third["instrument"] == "XAUUSDm" and third["topic"] == "pullback"


async def test_fallback_rotates_general_topics_without_inventing_pair_or_regime(workspace):
    first = await plan(workspace)
    await workspace.record(first)
    second = await plan(workspace)
    assert first["basis"] == second["basis"] == "GENERAL_EDUCATION"
    assert first["query"] != second["query"]
    assert "regime" not in first and "instrument" not in first


async def test_malformed_selections_do_not_break_the_optional_query_preview(workspace):
    selection = await workspace.selection()
    await workspace.store.update(selection, {**selection.data, "candidate": None})
    assert (await plan(workspace))["basis"] == "GENERAL_EDUCATION"


async def test_unknown_regime_does_not_invent_a_trend_in_query(workspace):
    await workspace.selection(regime="NOT_TRENDING")
    chosen = await plan(workspace)
    assert "trending market" not in chosen["query"]
    assert chosen["regime"] == "NOT_TRENDING"


@pytest.mark.parametrize("age", [73, -1])
async def test_stale_or_future_fingerprint_is_not_used_as_current_regime(workspace, age):
    await workspace.selection(age=age)
    assert (await plan(workspace))["basis"] == "GENERAL_EDUCATION"


async def test_current_cycle_creation_order_wins_over_old_selection_updates(workspace):
    old = await workspace.selection("EUR/USD")
    new_run = await workspace.store.create(
        "research_run",
        workspace.owner,
        {
            "account_id": str(workspace.account.id),
        },
        state="DEGRADED",
    )
    new_run.created_at = NOW + timedelta(days=1)
    await workspace.selection("XAUUSD", "RANGING", research_run=new_run)
    await workspace.store.update(old, {**old.data, "touched": True})
    chosen = await plan(workspace)
    assert chosen["instrument"] == "XAUUSD" and chosen["market_research_run_id"] == str(new_run.id)


async def test_new_in_progress_cycle_does_not_hide_last_finished_basis(workspace):
    await workspace.selection()
    await workspace.store.create(
        "research_run",
        workspace.owner,
        {
            "account_id": str(workspace.account.id),
        },
        state="RESEARCHING",
    )
    assert (await plan(workspace))["instrument"] == "EUR/USD"


async def test_plans_are_owner_scoped_and_do_not_use_inactive_accounts(workspace):
    foreign = uuid4()
    foreign_account = await workspace.store.create("account", foreign, {})
    foreign_run = await workspace.store.create(
        "research_run",
        foreign,
        {
            "account_id": str(foreign_account.id),
        },
        state="COMPLETED",
    )
    await workspace.selection(
        "XAUUSD", owner_id=foreign, account_id=foreign_account.id, research_run=foreign_run
    )
    assert (await plan(workspace))["basis"] == "GENERAL_EDUCATION"
    await workspace.selection()
    await workspace.store.update(workspace.account, state="DISABLED")
    assert (await plan(workspace))["basis"] == "GENERAL_EDUCATION"


async def test_query_rotation_is_bounded_to_four_highest_ranked_current_pairs(workspace):
    for index, symbol in enumerate(["EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY", "USD/CHF"]):
        await workspace.selection(symbol, score=95 - index)
    instruments = []
    for _ in range(8):
        chosen = await plan(workspace)
        instruments.append(chosen["instrument"])
        await workspace.record(chosen)
    assert set(instruments) == {"EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY"}
    assert instruments[:4] == instruments[4:]


async def test_legacy_and_explicit_fixed_queries_are_preserved(workspace):
    for schedule in (
        {"query": "my custom method"},
        {"query_mode": "FIXED", "query": "gold breakout"},
    ):
        result = await choose_scheduled_query(workspace.db, workspace.owner, schedule, now=NOW)
        assert result["mode"] == "FIXED" and result["query"] == schedule["query"]


async def test_schedule_api_defaults_to_auto_and_returns_preview_without_search(workspace):
    initial = (await workspace.client.get("/knowledge/youtube/schedule")).json()
    assert initial["query_mode"] == "AUTO_MARKET" and initial["query_preview"]["query"]
    saved = await workspace.client.put("/knowledge/youtube/schedule", json={"enabled": False})
    assert saved.status_code == 200, saved.text
    assert saved.json()["query_mode"] == "AUTO_MARKET"
    assert saved.json()["query_preview"]["mode"] == "AUTO_MARKET"
    assert not await workspace.store.list("youtube_discovery_run", workspace.owner)
    invalid = await workspace.client.put(
        "/knowledge/youtube/schedule", json={"query_mode": "unknown"}
    )
    assert invalid.status_code == 422


async def test_scheduler_persists_exact_query_and_basis_without_duplicate_runs(
    workspace, monkeypatch
):
    await workspace.selection()
    await workspace.store.create(
        "youtube_discovery_schedule",
        workspace.owner,
        {
            "enabled": True,
            "run_at": "00:00",
            "timezone": "UTC",
            "weekdays": list(range(7)),
            "query_mode": "AUTO_MARKET",
            "limit": 5,
        },
    )

    class Clock:
        @staticmethod
        def now(timezone):
            return NOW

    @asynccontextmanager
    async def unit_of_work():
        yield workspace.db

    queued = []
    monkeypatch.setattr(tasks, "datetime", Clock)
    monkeypatch.setattr(tasks, "unit_of_work", unit_of_work)
    monkeypatch.setattr(tasks.run_youtube_discovery, "delay", queued.append)
    first = await tasks._create_scheduled_youtube_runs()
    second = await tasks._create_scheduled_youtube_runs()
    assert first == queued and len(first) == 1 and not second
    run = (await workspace.store.list("youtube_discovery_run", workspace.owner))[0]
    assert run.data["query"] == run.data["query_plan"]["query"]
    assert run.data["query_plan"]["market_research_run_id"] == str(workspace.run.id)
    assert run.data["query_plan"]["topic"] == "trend"
    assert run.data["limit"] == 5
