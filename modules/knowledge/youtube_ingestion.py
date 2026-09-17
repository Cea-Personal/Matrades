from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.connections.models import ConnectionProvider
from modules.connections.resolution import find_connection
from modules.knowledge.ingestion import build_source_data
from modules.knowledge.openai_embeddings import embed_source_data
from modules.knowledge.youtube import YouTubeVideo, fetch_video_transcripts, serpapi_search
from packages.shared.store import ResourceStore


async def discover_youtube_videos(
    session: AsyncSession,
    owner_id: UUID,
    *,
    query: str,
    limit: int,
) -> list[YouTubeVideo]:
    """Perform only the SerpApi search stage."""
    connection = await find_connection(session, owner_id, ConnectionProvider.SERPAPI)
    if connection is None or not connection.secret:
        raise RuntimeError("configure an active SerpApi connection first")
    return await serpapi_search(connection.secret, query, limit=limit)


def _video_data(video: YouTubeVideo) -> dict[str, str]:
    return {
        "video_id": video.video_id,
        "url": video.url,
        "title": video.title,
        "description": video.description,
    }


async def ingest_youtube_transcripts(
    session: AsyncSession,
    owner_id: UUID,
    videos: list[YouTubeVideo],
    *,
    languages: list[str],
    category: str,
    actor_id: UUID | None = None,
) -> dict[str, Any]:
    """Fetch transcripts for searched videos and index them as knowledge."""
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
    results = await fetch_video_transcripts(
        videos, languages=languages, skip_video_ids=existing_ids
    )
    created: list[dict[str, Any]] = []
    skipped = 0
    failed: list[dict[str, Any]] = []
    transcript_results: list[dict[str, Any]] = []
    for result in results:
        video = result["video"]
        if result.get("error") == "already_scraped":
            skipped += 1
            transcript_results.append(
                {**_video_data(video), "status": "ALREADY_INGESTED", "language": None}
            )
            continue
        transcript = result.get("transcript")
        if not transcript:
            error = result.get("error") or "transcript_unavailable"
            failed.append({"video_id": video.video_id, "title": video.title, "error": error})
            transcript_results.append(
                {
                    **_video_data(video),
                    "status": "TRANSCRIPT_FAILED",
                    "language": None,
                    "error": error,
                }
            )
            continue
        content = f"{video.title}\n\n{video.description}\n\n{transcript}".strip()
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        if video.video_id in existing_ids or content_hash in existing_hashes:
            skipped += 1
            transcript_results.append(
                {
                    **_video_data(video),
                    "status": "ALREADY_INGESTED",
                    "language": result.get("language"),
                }
            )
            continue
        data = await embed_source_data(
            session,
            owner_id,
            build_source_data(
                name=video.title,
                content=content,
                category=category,
                tags=["youtube", "transcript", "trading"],
                source_kind="YOUTUBE_TRANSCRIPT",
                source_url=video.url,
                external_id=video.video_id,
            ),
        )
        data["transcript_language"] = result.get("language")
        data["discovery_stage"] = "SERPAPI_YOUTUBE_SEARCH"
        item = await store.create(
            "knowledge_source",
            owner_id,
            data,
            state="ACTIVE",
            actor_id=actor_id,
            event_type="knowledge_youtube_transcript.ingested",
        )
        created.append(item.public())
        existing_ids.add(video.video_id)
        existing_hashes.add(content_hash)
        transcript_results.append(
            {
                **_video_data(video),
                "status": "INGESTED",
                "language": result.get("language"),
                "source_id": str(item.id),
            }
        )
    return {
        "discovered": len(videos),
        "created": len(created),
        "skipped": skipped,
        "failed": failed,
        "transcript_results": transcript_results,
        "sources": [
            {key: value for key, value in item.items() if key != "segments"} for item in created
        ],
    }


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
    videos = await discover_youtube_videos(session, owner_id, query=query, limit=limit)
    return {
        "query": query,
        **await ingest_youtube_transcripts(
            session,
            owner_id,
            videos,
            languages=languages,
            category=category,
            actor_id=actor_id,
        ),
    }
