from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import current_actor, get_db
from apps.api.app.routes import knowledge
from modules.connections.resolution import _cipher
from modules.identity.authorization import Actor, Role
from modules.knowledge import reranking
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


@pytest.fixture
async def workspace(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        actor = Actor(uuid4(), uuid4(), Role.OWNER)
        app = FastAPI()
        app.include_router(knowledge.router)

        async def session():
            yield db

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[current_actor] = lambda: actor
        store = ResourceStore(db)

        async def create_connection(owner_id=actor.owner_id, provider="COHERE", active=True):
            credential = await store.create(
                "credential",
                owner_id,
                {
                    "provider": provider,
                    "envelope": _cipher().encrypt(owner_id, "owner-test-secret").as_dict(),
                },
            )
            return await store.create(
                "connection",
                owner_id,
                {
                    "name": "Reranking",
                    "provider": provider,
                    "active": active,
                    "credential_id": str(credential.id),
                    "configuration": {},
                },
            )

        connection = await create_connection()
        verification = AsyncMock(return_value=[(0, 0.99)])
        monkeypatch.setattr(knowledge, "cohere_rerank", verification)
        rerank = AsyncMock(
            side_effect=lambda key, query, documents, **kwargs: [
                (index, 0.95 - position * 0.01)
                for position, index in enumerate(reversed(range(len(documents))))
            ][: kwargs["top_n"]]
        )
        monkeypatch.setattr(reranking, "cohere_rerank", rerank)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield SimpleNamespace(
                client=client,
                actor=actor,
                store=store,
                db=db,
                app=app,
                connection=connection,
                create_connection=create_connection,
                verification=verification,
                rerank=rerank,
            )
    await engine.dispose()


async def enable(workspace, **patch):
    response = await workspace.client.put(
        "/knowledge/reranking-configuration",
        json={
            "connection_id": str(workspace.connection.id),
            "model": "rerank-v4.0-fast",
            "candidate_limit": 20,
            **patch,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def seed_source(workspace, name, *, owner_id=None, state="ACTIVE", **metadata):
    data = knowledge._document_data(
        knowledge.SourceInput(
            name=name,
            content=f"risk evidence {name}",
            category="trading",
            tags=["allowed"],
            asset_class="FOREX",
            instrument_type="SPOT",
            venue_instrument_id="eurusd",
            source_date="2026-09-01",
            **metadata,
        )
    )
    data.update(specification_version_id=str(uuid4()), quantity_unit="UNITS")
    return await workspace.store.create(
        "knowledge_source",
        owner_id or workspace.actor.owner_id,
        data,
        state=state,
    )


async def test_configuration_verifies_updates_and_disables_without_reindexing(workspace):
    initial = (await workspace.client.get("/knowledge/reranking-configuration")).json()
    assert not initial["configured"]
    configured = await enable(workspace)
    assert configured["configured"] and configured["verified_at"]
    assert "owner-test-secret" not in str(configured)
    workspace.verification.assert_awaited_once()
    assert workspace.verification.call_args.args[0] == "owner-test-secret"
    assert workspace.verification.call_args.kwargs["model"] == "rerank-v4.0-fast"
    source = await seed_source(workspace, "kept")
    before = dict(source.data)
    await enable(workspace, model="rerank-v3.5", candidate_limit=30)
    assert source.data == before and source.version == 1
    assert (
        len(
            await workspace.store.list(
                "knowledge_reranking_configuration", workspace.actor.owner_id
            )
        )
        == 1
    )
    disabled = await workspace.client.delete("/knowledge/reranking-configuration")
    assert disabled.status_code == 200 and not disabled.json()["configured"]
    await workspace.client.post("/knowledge/search", json={"query": "risk"})
    workspace.rerank.assert_not_awaited()


async def test_reranks_larger_pool_before_limit_and_preserves_citations_and_audit(workspace):
    await enable(workspace)
    first = await seed_source(workspace, "a")
    second = await seed_source(workspace, "b")
    third = await seed_source(workspace, "c")
    baseline = (
        await workspace.client.post("/knowledge/search", json={"query": "risk", "limit": 1})
    ).json()
    assert len(workspace.rerank.call_args.args[2]) == 3
    expected = next(
        item
        for item in [first, second, third]
        if item.data["segments"][0]["text"] == workspace.rerank.call_args.args[2][-1]
    )
    assert len(baseline["citations"]) == 1
    hit = baseline["citations"][0]
    assert hit["source_id"] == str(expected.id)
    assert hit["segment_id"] == expected.data["segments"][0]["id"]
    assert hit["text"] == expected.data["segments"][0]["text"]
    assert hit["score"] == hit["rerank_score"] == 0.95
    assert "hybrid_score" in hit and "vector_score" in hit
    assert baseline["reranking"]["status"] == "APPLIED"
    assert baseline["authority"] == "CONTEXT_ONLY" and not baseline["may_replace_facts"]
    answer = (
        await workspace.client.post("/knowledge/assistant", json={"question": "risk", "limit": 2})
    ).json()
    assert answer["status"] == "ANSWERED"
    assert answer["citations"][0]["source_id"] == str(expected.id)
    assert answer["claims"][0]["citation_indexes"] == [0]
    assert answer["reranking"]["status"] == "APPLIED"
    from sqlalchemy import select

    from packages.shared.store import AuditRecord

    audits = (
        await workspace.db.scalars(
            select(AuditRecord).where(AuditRecord.event_type == "knowledge.retrieved")
        )
    ).all()
    assert audits[-1].evidence["reranking"]["status"] == "APPLIED"
    assert "owner-test-secret" not in str([item.evidence for item in audits])


async def test_owner_lifecycle_and_all_metadata_filters_apply_before_external_call(workspace):
    await enable(workspace)
    allowed = await seed_source(workspace, "allowed")
    await seed_source(workspace, "foreign", owner_id=uuid4())
    await seed_source(workspace, "disabled", state="DISABLED")
    await seed_source(workspace, "deleted", state="DELETED")
    for field, value in [
        ("category", "other"),
        ("tags", ["private"]),
        ("asset_class", "METALS"),
        ("instrument_type", "CFD"),
        ("venue_instrument_id", "other"),
        ("source_date", "2025-01-01"),
        ("source_date", "2027-01-01"),
    ]:
        item = await seed_source(workspace, f"filtered-{field}-{value}")
        await workspace.store.update(item, {**item.data, field: value})
    response = await workspace.client.post(
        "/knowledge/search",
        json={
            "query": "risk",
            "category": "trading",
            "tags": ["allowed"],
            "asset_class": "FOREX",
            "instrument_type": "SPOT",
            "venue_instrument_id": "eurusd",
            "source_date_from": "2026-01-01",
            "source_date_to": "2026-12-31",
        },
    )
    assert response.status_code == 200
    assert workspace.rerank.call_args.args[2] == [allowed.data["segments"][0]["text"]]


async def test_empty_results_skip_provider_and_candidates_are_bounded(workspace):
    await enable(workspace)
    response = (await workspace.client.post("/knowledge/search", json={"query": "risk"})).json()
    assert response["reranking"]["status"] == "SKIPPED"
    workspace.rerank.assert_not_awaited()
    for index in range(25):
        await seed_source(workspace, str(index))
    response = await workspace.client.post("/knowledge/search", json={"query": "risk", "limit": 5})
    assert response.status_code == 200 and len(response.json()["citations"]) == 5
    assert len(workspace.rerank.call_args.args[2]) == 20


async def test_provider_failure_falls_back_and_marks_answer_degraded(workspace):
    await seed_source(workspace, "a")
    await seed_source(workspace, "b")
    baseline = (await workspace.client.post("/knowledge/search", json={"query": "risk"})).json()
    await enable(workspace)
    workspace.rerank.side_effect = RuntimeError("secret raw provider error")
    result = (await workspace.client.post("/knowledge/search", json={"query": "risk"})).json()
    assert result["citations"] == baseline["citations"]
    assert result["reranking"]["status"] == "DEGRADED"
    assert "secret raw" not in str(result)
    answer = (await workspace.client.post("/knowledge/assistant", json={"question": "risk"})).json()
    assert answer["status"] == "DEGRADED"
    assert answer["citations"][0]["source_id"] == baseline["citations"][0]["source_id"]


@pytest.mark.parametrize("kind", ["foreign", "disabled", "wrong_provider", "missing"])
async def test_rejects_unusable_connections_without_external_calls(workspace, kind):
    connection_id = uuid4()
    if kind != "missing":
        connection = await workspace.create_connection(
            owner_id=uuid4() if kind == "foreign" else workspace.actor.owner_id,
            provider="OPENAI" if kind == "wrong_provider" else "COHERE",
            active=kind != "disabled",
        )
        connection_id = connection.id
    result = await workspace.client.put(
        "/knowledge/reranking-configuration", json={"connection_id": str(connection_id)}
    )
    assert result.status_code == 422
    workspace.verification.assert_not_awaited()


async def test_failed_verification_preserves_current_configuration(workspace):
    await enable(workspace)
    workspace.verification.side_effect = RuntimeError("private provider error")
    result = await workspace.client.put(
        "/knowledge/reranking-configuration",
        json={
            "connection_id": str(workspace.connection.id),
            "model": "rerank-v3.5",
        },
    )
    assert result.status_code == 422 and "private provider" not in result.text
    current = (await workspace.client.get("/knowledge/reranking-configuration")).json()
    assert current["model"] == "rerank-v4.0-fast"


async def test_viewer_cannot_mutate_and_other_owner_has_no_configuration(workspace):
    await enable(workspace)
    workspace.app.dependency_overrides[current_actor] = lambda: Actor(
        uuid4(), workspace.actor.owner_id, Role.VIEWER
    )
    assert (await workspace.client.delete("/knowledge/reranking-configuration")).status_code == 403
    assert (
        await workspace.client.put(
            "/knowledge/reranking-configuration",
            json={"connection_id": str(workspace.connection.id)},
        )
    ).status_code == 403
    workspace.app.dependency_overrides[current_actor] = lambda: Actor(uuid4(), uuid4(), Role.OWNER)
    assert not (await workspace.client.get("/knowledge/reranking-configuration")).json()[
        "configured"
    ]


async def test_disabled_connection_at_runtime_falls_back_without_transmitting(workspace):
    await enable(workspace)
    await seed_source(workspace, "a")
    await workspace.store.update(
        workspace.connection, {**workspace.connection.data, "active": False}
    )
    result = (await workspace.client.post("/knowledge/search", json={"query": "risk"})).json()
    assert result["reranking"]["status"] == "DEGRADED" and result["citations"]
    workspace.rerank.assert_not_awaited()
