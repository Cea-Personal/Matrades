from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.connections.models import ConnectionProvider
from modules.connections.resolution import find_connection
from modules.knowledge.ingestion import build_source_data
from modules.knowledge.openai_embeddings import embed_source_data
from modules.knowledge.youtube import scrape_youtube_transcripts
from packages.shared.store import ResourceStore


async def ingest_youtube_discovery(
    session: AsyncSession,
    owner_id: UUID,
    *,
    query: str,
    limit: int,
    languages: list[str],
    category: str,
    actor_id: UUID | None = None,
) -> dict[str, Any]:
    connection = await find_connection(session, owner_id, ConnectionProvider.SERPAPI)
    if connection is None or not connection.secret:
        raise RuntimeError("configure an active SerpApi connection first")
    store = ResourceStore(session)
    existing = await store.list("knowledge_source", owner_id)
    existing_ids = {
        str(item.data.get("external_id"))
        for item in existing
        if item.data.get("source_kind") == "YOUTUBE_TRANSCRIPT"
    }
    existing_hashes = {
        str(item.data.get("content_hash"))
        for item in existing
        if item.data.get("source_kind") == "YOUTUBE_TRANSCRIPT"
    }
    results = await scrape_youtube_transcripts(
        connection.secret,
        query,
        limit=limit,
        languages=languages,
        skip_video_ids=existing_ids,
    )
    created: list[dict[str, Any]] = []
    skipped = 0
    failed: list[dict[str, Any]] = []
    for result in results:
        video = result["video"]
        transcript = result.get("transcript")
        if result.get("error") == "already_scraped":
            skipped += 1
            continue
        if not transcript:
            failed.append(
                {"video_id": video.video_id, "title": video.title, "error": result.get("error")}
            )
            continue
        content = f"{video.title}\n\n{video.description}\n\n{transcript}".strip()
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        if video.video_id in existing_ids or content_hash in existing_hashes:
            skipped += 1
            continue
        data = await embed_source_data(session, owner_id, build_source_data(
            name=video.title,
            content=content,
            category=category,
            tags=["youtube", "transcript", "trading"],
            source_kind="YOUTUBE_TRANSCRIPT",
            source_url=video.url,
            external_id=video.video_id,
        ))
        item = await store.create(
            "knowledge_source",
            owner_id,
            data,
            state="ACTIVE",
            actor_id=actor_id,
            event_type="knowledge_youtube_ingestion.completed",
        )
        created.append(item.public())
        existing_ids.add(video.video_id)
        existing_hashes.add(content_hash)
    return {
        "query": query,
        "discovered": len(results),
        "created": len(created),
        "skipped": skipped,
        "failed": failed,
        "sources": [
            {key: value for key, value in item.items() if key != "segments"} for item in created
        ],
    }
