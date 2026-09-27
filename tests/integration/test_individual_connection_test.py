from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import current_actor, get_db
from apps.api.app.routes import configuration
from modules.connections.models import ConnectionProbe, ConnectionProfile, ConnectionProvider
from modules.identity.authorization import Actor, Role
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


@pytest.fixture
async def workspace(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db, db.begin():
            actor = Actor(uuid4(), uuid4(), Role.OWNER)
            app = FastAPI()
            app.include_router(configuration.router, prefix="/api/v1")

            async def session():
                yield db

            app.dependency_overrides[get_db] = session
            app.dependency_overrides[current_actor] = lambda: actor
            store = ResourceStore(db)
            probe = AsyncMock(
                return_value=ConnectionProbe(
                    status="HEALTHY",
                    latency_ms=1,
                    checked_at=datetime.now(UTC).isoformat(),
                    fresh=True,
                    writes=False,
                )
            )
            monkeypatch.setattr(configuration, "probe_connection", probe)

            async def create_pair(provider=ConnectionProvider.COINBASE, **patch):
                credential_id = None
                if provider in {
                    ConnectionProvider.TWELVE_DATA,
                    ConnectionProvider.COHERE,
                    ConnectionProvider.MT5_BRIDGE,
                }:
                    credential = await store.create(
                        "credential",
                        actor.owner_id,
                        {
                            "provider": provider.value,
                            "status": "UNTESTED",
                            "envelope": configuration._cipher()
                            .encrypt(actor.owner_id, "synthetic-test-secret")
                            .as_dict(),
                        },
                    )
                    credential_id = credential.id
                profile = ConnectionProfile(
                    name="Selected source",
                    provider=provider,
                    credential_id=credential_id,
                    configuration=(
                        {"bridge_url": "http://127.0.0.1:8765"}
                        if provider is ConnectionProvider.MT5_BRIDGE
                        else {}
                    ),
                )
                data = {**profile.model_dump(mode="json"), "health": "UNTESTED"}
                selected = await store.create("connection", actor.owner_id, {**data, **patch})
                other = await store.create(
                    "connection", actor.owner_id, {**data, "name": "Other source"}
                )
                return selected, other

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield SimpleNamespace(
                    client=client,
                    store=store,
                    actor=actor,
                    probe=probe,
                    create_pair=create_pair,
                )
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "provider",
    [
        ConnectionProvider.COINBASE,
        ConnectionProvider.TWELVE_DATA,
        ConnectionProvider.COHERE,
        ConnectionProvider.MT5_BRIDGE,
    ],
)
async def test_http_source_test_probes_only_selected_connection_even_with_shared_credential(
    workspace, provider
):
    selected, other = await workspace.create_pair(provider)
    other_before = dict(other.data)
    response = await workspace.client.post(f"/api/v1/configuration/connections/{selected.id}/test")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(selected.id)
    assert response.json()["health"] == "HEALTHY"
    workspace.probe.assert_awaited_once()
    profile, secret = workspace.probe.call_args.args
    assert profile.name == "Selected source" and profile.provider is provider
    assert secret == ("synthetic-test-secret" if selected.data["credential_id"] else None)
    assert other.data == other_before and other.version == 1


async def test_cached_twelve_data_source_does_not_probe_any_connection(workspace):
    selected, other = await workspace.create_pair(
        ConnectionProvider.TWELVE_DATA,
        health="HEALTHY",
        last_checked=datetime.now(UTC).isoformat(),
    )
    response = await workspace.client.post(f"/api/v1/configuration/connections/{selected.id}/test")
    assert response.status_code == 200
    assert response.json()["health_cached"] is True
    assert response.json()["id"] == str(selected.id)
    workspace.probe.assert_not_awaited()
    assert other.data["health"] == "UNTESTED" and other.version == 1


async def test_source_probe_failure_does_not_fall_back_to_testing_other_sources(workspace):
    selected, other = await workspace.create_pair()
    workspace.probe.side_effect = ValueError("Provider timed out")
    response = await workspace.client.post(f"/api/v1/configuration/connections/{selected.id}/test")
    assert response.status_code == 422
    workspace.probe.assert_awaited_once()
    assert workspace.probe.call_args.args[0].name == "Selected source"
    assert other.data["health"] == "UNTESTED" and other.version == 1


async def test_foreign_source_cannot_be_tested(workspace):
    foreign = await workspace.store.create(
        "connection",
        uuid4(),
        ConnectionProfile(name="Foreign source", provider=ConnectionProvider.COINBASE).model_dump(
            mode="json"
        ),
    )
    response = await workspace.client.post(f"/api/v1/configuration/connections/{foreign.id}/test")
    assert response.status_code == 404
    workspace.probe.assert_not_awaited()
