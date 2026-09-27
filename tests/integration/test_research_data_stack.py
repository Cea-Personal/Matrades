from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import current_actor, get_db
from apps.api.app.routes import research_data as routes
from apps.worker.app.tasks import research_data as imports_worker
from modules.connections.models import ConnectionProfile
from modules.connections.resolution import ResolvedConnection
from modules.identity.authorization import Actor, Role
from modules.market_data import research_context, research_history
from modules.market_data.research_store import ResearchDataStore
from modules.research.quantitative_features import candle_frame
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore
from tests.unit.test_pair_strategy_library import history


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

    monkeypatch.setattr(imports_worker, "unit_of_work", uow)
    monkeypatch.setattr(research_history.settings, "research_data_root", tmp_path)
    yield uow
    await engine.dispose()


async def seed(db, owner, provider="DUKASCOPY", purpose="HISTORY", capability="CANDLES"):
    store = ResourceStore(db)
    account = await store.create("account", owner, {"name": "Demo"})
    connection = await store.create(
        "connection",
        owner,
        {
            "name": "Public",
            "provider": provider,
            "active": True,
            "configuration": {
                "symbol_map": {"EUR/USD": {"symbol": "EURUSD", "price_scale": "100000"}}
            },
        },
    )
    binding = await store.create(
        "provider_binding",
        owner,
        {
            "account_id": str(account.id),
            "connection_id": str(connection.id),
            "lane": {"asset_class": "FOREX", "instrument_type": "CFD"},
            "verification_status": "VERIFIED",
            "authority_purpose": purpose,
            "capability": capability,
        },
    )
    return account, connection, binding


async def test_import_api_requires_verified_candles_and_owner_role(database, monkeypatch):
    owner = uuid4()
    actor = Actor(uuid4(), owner, Role.OWNER)
    async with database() as db:
        account, connection, binding = await seed(db, owner, capability="CFTC_COT")
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[current_actor] = lambda: actor

    async def get_session():
        async with database() as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    dispatched = []
    monkeypatch.setattr(
        imports_worker.ingest_research_history, "apply_async", lambda **kw: dispatched.append(kw)
    )
    now = datetime.now(UTC)
    payload = {
        "account_id": str(account.id),
        "connection_id": str(connection.id),
        "instrument": "EUR/USD",
        "start_at": (now - timedelta(days=1)).isoformat(),
        "end_at": now.isoformat(),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (await client.post("/research-data/imports", json=payload)).status_code == 409
        assert not dispatched
        async with database() as db:
            item = await ResourceStore(db).get("provider_binding", binding.id, owner)
            await ResourceStore(db).update(item, {**item.data, "capability": "CANDLES"})
        response = await client.post("/research-data/imports", json=payload)
        assert response.status_code == 202 and response.json()["state"] == "QUEUED"
        assert len(dispatched) == 1
        app.dependency_overrides[current_actor] = lambda: Actor(uuid4(), owner, Role.VIEWER)
        assert (await client.post("/research-data/imports", json=payload)).status_code == 403
        app.dependency_overrides[current_actor] = lambda: Actor(uuid4(), uuid4(), Role.OWNER)
        assert (await client.get("/research-data/imports")).json() == []
        assert (await client.post("/research-data/imports", json=payload)).status_code == 404
        assert len(dispatched) == 1


async def test_experiment_archive_cannot_be_read_by_other_owner(database, monkeypatch, tmp_path):
    owner = uuid4()
    async with database() as db:
        reference = ResearchDataStore(tmp_path, owner).json(
            {"experiments": []}, layer="experiments"
        )
        record = await ResourceStore(db).create(
            "strategy_experiment", owner, {"archive": reference}
        )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[current_actor] = lambda: Actor(uuid4(), uuid4(), Role.OWNER)

    async def get_session():
        async with database() as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (
            await client.get(f"/research-data/experiments/{record.id}/results")
        ).status_code == 404
        app.dependency_overrides[current_actor] = lambda: Actor(uuid4(), owner, Role.VIEWER)
        response = await client.get(f"/research-data/experiments/{record.id}/results")
        assert response.status_code == 200 and response.json() == {"experiments": []}


async def test_accumulated_cache_keeps_first_prices_and_pins_source_configuration(
    database, tmp_path
):
    owner, account, connection_id = uuid4(), uuid4(), uuid4()
    connection = ResolvedConnection(
        connection_id,
        ConnectionProfile(
            name="Duka",
            provider="DUKASCOPY",
            configuration={
                "symbol_map": {"EUR/USD": {"symbol": "EURUSD", "price_scale": "100000"}}
            },
        ),
        None,
    )
    values = history(100)
    async with database() as db:
        for start, end, candles in [(0, 60, values[:60]), (50, 100, values[50:])]:
            if start == 50:
                candles = [
                    c.model_copy(
                        update={
                            "open": c.open + Decimal(2),
                            "high": c.high + Decimal(2),
                            "low": c.low + Decimal(2),
                            "close": c.close + Decimal(2),
                        }
                    )
                    for c in candles
                ]
            source = {
                "normalized": ResearchDataStore(tmp_path, owner).frame(candle_frame(candles, 60)),
                "requested_start_at": values[start].observed_at.isoformat(),
                "requested_end_at": (
                    values[end - 1].observed_at + timedelta(minutes=1)
                ).isoformat(),
                "configuration_hash": research_history.configuration_hash(connection),
            }
            await research_history.persist_dataset(
                db, owner, account, connection_id, "EUR/USD", "1m", candles, source
            )
        args = (
            connection,
            "EUR/USD",
            values[0].observed_at,
            values[-1].observed_at + timedelta(minutes=1),
            "1m",
        )
        cached, source = await research_history.cached_history(db, owner, account, *args)
        assert len(cached) == 100 and len(source["cached_dataset_ids"]) == 2
        assert cached[55].close == values[55].close
        assert cached[65].close == values[65].close + 2
        assert source["execution_authority"] is False
        assert await research_history.cached_history(db, uuid4(), account, *args) is None
        assert await research_history.cached_history(db, owner, uuid4(), *args) is None
        connection.profile.configuration["symbol_map"]["EUR/USD"]["price_scale"] = "1000"
        assert await research_history.cached_history(db, owner, account, *args) is None


async def test_worker_import_is_replayable_and_rechecks_binding(database, monkeypatch):
    owner = uuid4()
    async with database() as db:
        account, connection, binding = await seed(db, owner)
        run = await ResourceStore(db).create(
            "research_data_import",
            owner,
            {
                "account_id": str(account.id),
                "connection_id": str(connection.id),
                "instrument": "EUR/USD",
                "timeframe": "1m",
                "start_at": history()[0].observed_at.isoformat(),
                "end_at": history()[-1].observed_at.isoformat(),
            },
            state="QUEUED",
        )
    calls = []

    async def load(connection, owner, instrument, start, end, timeframe, **kwargs):
        calls.append(instrument)
        candles = history(100)
        source = {
            "normalized": ResearchDataStore(
                research_history.settings.research_data_root, owner
            ).frame(candle_frame(candles, 60)),
            "configuration_hash": research_history.configuration_hash(connection),
            "requested_start_at": start.isoformat(),
            "requested_end_at": end.isoformat(),
        }
        return candles, source

    monkeypatch.setattr(imports_worker, "archived_history", load)
    assert (await imports_worker._ingest(run.id))["state"] == "COMPLETED"
    assert (await imports_worker._ingest(run.id))["state"] == "COMPLETED"
    assert calls == ["EUR/USD"]
    async with database() as db:
        store = ResourceStore(db)
        assert len(await store.list("market_dataset", owner)) == 1
        assert len(await store.list("market_features", owner)) == 1
        invalid = await store.create("research_data_import", owner, run.data, state="QUEUED")
        item = await store.get("provider_binding", binding.id, owner)
        await store.update(item, {**item.data, "verification_status": "NOT_VERIFIED"})
    with pytest.raises(ValueError, match="no longer verified"):
        await imports_worker._ingest(invalid.id)
    assert len(calls) == 1


async def test_current_context_cannot_leak_into_discovery_cut(database, monkeypatch):
    owner = uuid4()
    async with database() as db:
        account, connection, _ = await seed(
            db, owner, provider="ECB", purpose="REFERENCE", capability="CFTC_COT"
        )
        await ResourceStore(db).update(
            connection,
            {
                **connection.data,
                "configuration": {"series": [{"flow": "EXR", "key": "D.USD.EUR.SP00.A"}]},
            },
        )
        now = datetime.now(UTC)

        async def context(*_):
            return {
                "flow": "EXR",
                "key": "D.USD.EUR.SP00.A",
                "observations": [{"OBS_VALUE": "1.25"}],
                "available_at": now.isoformat(),
                "point_in_time": "FIRST_SEEN_ONLY",
            }

        monkeypatch.setattr(research_context, "ecb_series", context)
        result, proxies = await research_context.collect_context(
            db, owner, account.id, "EUR/USD", now - timedelta(days=60), now - timedelta(days=1)
        )
        assert result["sources"][0]["status"] == "WITHHELD_AFTER_DISCOVERY_CUT"
        assert result["sources"][0]["summary"] == {} and not proxies
        stored = (await ResourceStore(db).list("market_context", owner))[0]
        assert stored.data["summary"]["latest_observation"]["OBS_VALUE"] == "1.25"
        # On a later cycle, evidence that was already seen is eligible at its cutoff.
        result, _ = await research_context.collect_context(
            db, owner, account.id, "EUR/USD", now - timedelta(days=60), now + timedelta(minutes=1)
        )
        archived = [s for s in result["sources"] if s["status"] == "AVAILABLE_ARCHIVED"]
        assert len(archived) == 1
        assert archived[0]["visible_at_discovery_cut"] is True
        assert archived[0]["context_id"] == str(stored.id)
        await ResourceStore(db).update(connection, {**connection.data, "active": False})
        result, _ = await research_context.collect_context(
            db, owner, account.id, "EUR/USD", now - timedelta(days=60), now
        )
        assert result["sources"][0]["status"] == "UNAVAILABLE"
        assert result["sources"][0]["error_type"] == "RuntimeError"
