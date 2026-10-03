from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import current_actor, get_db
from apps.api.app.routes import provider_binding_assistance as assistance
from modules.connections.binding_assistance import BindingCandidate, select_candidates
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
            app.include_router(assistance.router, prefix="/api/v1")

            async def session():
                yield db

            app.dependency_overrides[get_db] = session
            app.dependency_overrides[current_actor] = lambda: actor
            store = ResourceStore(db)
            account = await store.create(
                "account", actor.owner_id, {"name": "Primary", "currency": "USD"}
            )
            other_account = await store.create("account", actor.owner_id, {"name": "Secondary"})
            for item, asset in ((account, "FOREX"), (other_account, "CRYPTOCURRENCY")):
                await store.create(
                    "research_matrix",
                    actor.owner_id,
                    {
                        "account_id": str(item.id),
                        "version": 1,
                        "lanes": [
                            {"asset_class": asset, "instrument_type": "CFD", "enabled": True}
                        ],
                    },
                )
            source = await store.create(
                "connection",
                actor.owner_id,
                {
                    "name": "Forex provider",
                    "provider": "TWELVE_DATA",
                    "active": True,
                    "health": "HEALTHY",
                    "capabilities": ["market.discovery", "candles.read"],
                    "configuration": {
                        "api_key": "must-not-reach-ai",
                        "bridge_url": "https://private",
                    },
                },
            )

            async def advise(logical_id, payload, schema, **kwargs):
                assert logical_id == "knowledge_assistant"
                assert kwargs["owner_id"] == actor.owner_id
                assert "must-not-reach-ai" not in str(payload) and "https://private" not in str(
                    payload
                )
                options = [BindingCandidate.model_validate(item) for item in payload["options"]]
                return {
                    "choices": [
                        {
                            "candidate_id": c.candidate_id,
                            "reason": "Fits this lane's supported coverage.",
                        }
                        for c in select_candidates(options)
                    ]
                }

            gateway = SimpleNamespace(invoke=AsyncMock(side_effect=advise), close=AsyncMock())
            monkeypatch.setattr(assistance, "RedisAgentGateway", lambda *_: gateway)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield SimpleNamespace(
                    client=client,
                    db=db,
                    store=store,
                    actor=actor,
                    app=app,
                    account=account,
                    other_account=other_account,
                    source=source,
                    gateway=gateway,
                )
    finally:
        await engine.dispose()


def base(workspace, account=None):
    return f"/api/v1/accounts/{(account or workspace.account).id}/provider-binding-suggestions"


async def generate(workspace):
    response = await workspace.client.post(base(workspace))
    assert response.status_code == 200, response.text
    return response.json()


def apply_input(plan):
    return {
        "recommendation_id": plan["id"],
        "candidate_ids": [s["candidate_id"] for s in plan["suggestions"]],
    }


async def test_review_is_read_only_then_application_is_verified_account_scoped_and_idempotent(
    workspace,
):
    plan = await generate(workspace)
    assert plan["mode"] == "AI_ASSISTED" and plan["matrix_version"] == 1
    assert await workspace.store.list("provider_binding", workspace.actor.owner_id) == []
    response = await workspace.client.post(base(workspace) + "/apply", json=apply_input(plan))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verified_count"] == 2 and result["unverified_count"] == 0
    assert all(b["account_id"] == str(workspace.account.id) for b in result["bindings"])
    repeat = await workspace.client.post(base(workspace) + "/apply", json=apply_input(plan))
    assert repeat.status_code == 200 and repeat.json() == result
    assert len(await workspace.store.list("provider_binding", workspace.actor.owner_id)) == 2
    refreshed = await generate(workspace)
    assert all(s["status"] == "ALREADY_BOUND" for s in refreshed["suggestions"])
    workspace.gateway.invoke.assert_awaited_once()
    assert (await workspace.client.get(base(workspace, workspace.other_account))).json() is None


@pytest.mark.parametrize("change", ["connection", "matrix", "binding"])
async def test_changed_configuration_rejects_stale_suggestions_without_writes(workspace, change):
    plan = await generate(workspace)
    if change == "connection":
        await workspace.store.update(
            workspace.source, {**workspace.source.data, "health": "OFFLINE"}
        )
    elif change == "matrix":
        await workspace.store.create(
            "research_matrix",
            workspace.actor.owner_id,
            {
                "account_id": str(workspace.account.id),
                "version": 2,
                "lanes": [{"asset_class": "METALS", "instrument_type": "CFD", "enabled": True}],
            },
        )
    else:
        await workspace.store.create(
            "provider_binding", workspace.actor.owner_id, {"account_id": str(workspace.account.id)}
        )
    before = len(await workspace.store.list("provider_binding", workspace.actor.owner_id))
    assert (await workspace.client.get(base(workspace))).json()["stale"] is True
    response = await workspace.client.post(base(workspace) + "/apply", json=apply_input(plan))
    assert response.status_code == 409 and "configuration changed" in response.json()["detail"]
    assert len(await workspace.store.list("provider_binding", workspace.actor.owner_id)) == before


async def test_untested_connection_is_never_verified_by_ai(workspace):
    await workspace.store.update(
        workspace.source, {**workspace.source.data, "health": "UNTESTED", "capabilities": []}
    )
    plan = await generate(workspace)
    assert all(s["status"] == "NEEDS_TEST" for s in plan["suggestions"])
    response = await workspace.client.post(base(workspace) + "/apply", json=apply_input(plan))
    assert response.status_code == 200
    assert response.json()["unverified_count"] == 2 and response.json()["verified_count"] == 0


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("deadline"), {"choices": [{"candidate_id": "invented", "reason": "invented"}]}],
)
async def test_ai_failure_has_explicit_rule_based_fallback(workspace, failure):
    workspace.gateway.invoke.side_effect = failure if isinstance(failure, Exception) else None
    workspace.gateway.invoke.return_value = failure
    plan = await generate(workspace)
    assert plan["mode"] == "RULE_BASED" and "AI assistance was unavailable" in plan["message"]
    assert {s["provider"] for s in plan["suggestions"]} == {"TWELVE_DATA"}
    workspace.gateway.close.assert_awaited_once()


async def test_foreign_accounts_and_cross_account_recommendations_are_rejected(workspace):
    foreign = await workspace.store.create("account", uuid4(), {"name": "Foreign"})
    assert (await workspace.client.post(base(workspace, foreign))).status_code == 404
    workspace.gateway.invoke.assert_not_awaited()
    plan = await generate(workspace)
    response = await workspace.client.post(
        base(workspace, workspace.other_account) + "/apply", json=apply_input(plan)
    )
    assert response.status_code == 404
    response = await workspace.client.post(
        base(workspace) + "/apply",
        json={"recommendation_id": plan["id"], "candidate_ids": ["invented"]},
    )
    assert response.status_code == 422
    assert await workspace.store.list("provider_binding", workspace.actor.owner_id) == []


async def test_disabled_matrix_lanes_are_not_recommended_and_gaps_are_reported(workspace):
    await workspace.store.create(
        "research_matrix",
        workspace.actor.owner_id,
        {
            "account_id": str(workspace.account.id),
            "version": 2,
            "lanes": [
                {"asset_class": "FOREX", "instrument_type": "CFD", "enabled": False},
                {"asset_class": "METALS", "instrument_type": "CFD", "enabled": True},
            ],
        },
    )
    plan = await generate(workspace)
    assert plan["suggestions"] == [] and plan["gaps"][0]["lane"] == "METALS:CFD"
    assert plan["matrix_version"] == 2
    workspace.gateway.invoke.assert_not_awaited()


async def test_viewer_can_read_but_cannot_generate_or_apply(workspace):
    plan = await generate(workspace)
    workspace.app.dependency_overrides[current_actor] = lambda: Actor(
        workspace.actor.actor_id, workspace.actor.owner_id, Role.VIEWER
    )
    assert (await workspace.client.get(base(workspace))).status_code == 200
    assert (await workspace.client.post(base(workspace))).status_code == 403
    assert (
        await workspace.client.post(base(workspace) + "/apply", json=apply_input(plan))
    ).status_code == 403
