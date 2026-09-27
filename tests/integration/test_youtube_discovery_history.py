from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import current_actor, get_db
from apps.api.app.routes import knowledge
from modules.identity.authorization import Actor, Role
from modules.knowledge import youtube, youtube_ingestion
from modules.knowledge.ingestion import build_source_data
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


@pytest.fixture
async def workspace(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        owner = uuid4()
        store = ResourceStore(db)
        connection = await store.create("connection", owner, {"provider": "SERPAPI"})

        async def resolve(session, owner_id, provider):
            return SimpleNamespace(
                id=connection.id, secret=str(uuid4()), profile=SimpleNamespace(id=uuid4())
            )

        monkeypatch.setattr(youtube_ingestion, "find_connection", resolve)
        real_discover = youtube.serpapi_discover
        calls = []

        async def handler(request):
            calls.append(int(request.url.params["start"]))
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {"title": f"Video {index}", "link": f"https://youtu.be/video_{index:03}"}
                        for index in range(10)
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as provider_client:

            async def discover(*args, **kwargs):
                return await real_discover(*args, **kwargs, client=provider_client)

            monkeypatch.setattr(youtube_ingestion, "serpapi_discover", discover)
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
                    owner=owner,
                    store=store,
                    client=client,
                    calls=calls,
                    connection_id=connection.id,
                )
    await engine.dispose()


async def search(workspace, query="forex strategy"):
    response = await workspace.client.post("/knowledge/youtube/search", json={"query": query})
    assert response.status_code == 201, response.text
    return response.json()


async def test_repeated_searches_find_unseen_results_then_return_empty(workspace):
    first, second, third = await search(workspace), await search(workspace), await search(workspace)
    assert first["discovered"] == second["discovered"] == 5
    assert third["discovered"] == 0
    assert not {item["video_id"] for item in first["videos"]} & {
        item["video_id"] for item in second["videos"]
    }
    assert len(await workspace.store.list("knowledge_source", workspace.owner)) == 0


async def test_history_is_owner_scoped_and_cross_query(workspace):
    first = await search(workspace)
    second = await search(workspace, "gold strategy")
    assert not {item["video_id"] for item in first["videos"]} & {
        item["video_id"] for item in second["videos"]
    }
    foreign = await youtube_ingestion.discover_youtube_videos(
        workspace.db,
        uuid4(),
        query="forex strategy",
        limit=5,
    )
    assert [item.video_id for item in foreign] == [item["video_id"] for item in first["videos"]]


async def test_one_stage_ingestion_reserves_results_even_without_run_history(workspace):
    first = await youtube_ingestion.discover_youtube_videos(
        workspace.db,
        workspace.owner,
        query="forex",
        limit=5,
    )
    second = await youtube_ingestion.discover_youtube_videos(
        workspace.db,
        workspace.owner,
        query="metals",
        limit=5,
    )
    assert len(first) == len(second) == 5
    assert not {item.video_id for item in first} & {item.video_id for item in second}


async def test_retry_partial_run_only_fetches_failed_transcripts(workspace, monkeypatch):
    discovered = await search(workspace)
    seen = []
    failed_id = discovered["videos"][0]["video_id"]

    async def fetch(video_id, languages):
        seen.append(video_id)
        if video_id == failed_id and seen.count(video_id) == 1:
            raise RuntimeError("captions unavailable")
        return f"{video_id} trend following strategy", "en"

    monkeypatch.setattr(youtube, "fetch_transcript", fetch)
    endpoint = f"/knowledge/youtube/runs/{discovered['run_id']}/transcripts"
    first = await workspace.client.post(endpoint)
    assert first.status_code == 200 and first.json()["state"] == "PARTIAL"
    assert first.json()["created"] == 4
    second = await workspace.client.post(endpoint)
    assert second.status_code == 200, second.text
    assert second.json()["state"] == "SUCCEEDED" and second.json()["created"] == 5
    assert seen == [item["video_id"] for item in discovered["videos"]] + [failed_id]
    third = await workspace.client.post(endpoint)
    assert third.json()["already_processed"]
    assert len(seen) == 6
    assert len(await workspace.store.list("knowledge_source", workspace.owner)) == 5


async def test_foreign_run_cannot_be_fetched_or_retried(workspace):
    foreign = await workspace.store.create("youtube_discovery_run", uuid4(), {}, state="PARTIAL")
    response = await workspace.client.post(f"/knowledge/youtube/runs/{foreign.id}/transcripts")
    assert response.status_code == 404


async def test_existing_indexed_videos_are_excluded_before_result_limit(workspace):
    await workspace.store.create(
        "knowledge_source",
        workspace.owner,
        build_source_data(
            name="Previously imported",
            content="Trend method",
            source_kind="YOUTUBE_TRANSCRIPT",
            external_id="video_000",
        ),
    )
    result = await search(workspace)
    assert result["discovered"] == 5
    assert "video_000" not in {item["video_id"] for item in result["videos"]}


async def test_discovery_locks_canonical_connection_id_not_generated_profile_id(
    workspace, monkeypatch
):
    scalar = AsyncMock(wraps=workspace.db.scalar)
    monkeypatch.setattr(workspace.db, "scalar", scalar)
    await youtube_ingestion.discover_youtube_videos(
        workspace.db,
        workspace.owner,
        query="forex",
        limit=5,
    )
    statement = scalar.call_args_list[0].args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "FOR UPDATE" in str(compiled)
    assert workspace.connection_id in compiled.params.values()
    assert workspace.owner in compiled.params.values()
