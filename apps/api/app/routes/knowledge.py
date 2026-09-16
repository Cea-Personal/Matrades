from __future__ import annotations

import hashlib
import io
import math
import re
import zipfile
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from xml.etree import ElementTree

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.blob_store.local import LocalBlobStore
from adapters.reranking.cohere import DEFAULT_MODEL as COHERE_MODEL
from adapters.reranking.cohere import cohere_rerank
from apps.api.app.dependencies import current_actor, get_db, require_roles, require_step_up
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import resolve_connection
from modules.identity.authorization import Actor, Role
from modules.knowledge.assistant import KnowledgeAssistant, KnowledgeQuestion
from modules.knowledge.ingestion import build_source_data
from modules.knowledge.models import RetrievalHit
from modules.knowledge.openai_embeddings import (
    DEFAULT_MODEL,
    embed_source_data,
    embed_texts_for_owner,
    openai_embeddings,
)
from modules.knowledge.reranking import RerankingConfigurationInput, rerank_for_owner
from modules.knowledge.youtube_ingestion import ingest_youtube_discovery
from modules.research.scheduling import default_schedule, next_run_at, normalize_schedule
from modules.security.platform import validate_upload
from packages.shared.config import get_settings
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])
assistant_router = APIRouter(prefix="/knowledge-assistant", tags=["Knowledge"])


class SourceInput(BaseModel):
    name: str
    content: str = ""
    media_type: str = "text/plain"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    source_date: str | None = None
    source_kind: str = "DOCUMENT"
    source_url: str | None = None
    external_id: str | None = None
    asset_class: str | None = None
    instrument_type: str | None = None
    venue_instrument_id: str | None = None
    specification_version_id: str | None = None
    source_cut_refs: list[str] = Field(default_factory=list)


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_date_from: str | None = None
    source_date_to: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
    asset_class: str | None = None
    instrument_type: str | None = None
    venue_instrument_id: str | None = None


class YouTubeScrapeInput(BaseModel):
    query: str = Field(min_length=2, max_length=240)
    limit: int = Field(default=5, ge=1, le=20)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    category: str = "trading"


class YouTubeScheduleInput(YouTubeScrapeInput):
    enabled: bool = True
    run_at: str = "05:00"
    timezone: str = "UTC"
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))

    @model_validator(mode="after")
    def valid_schedule(self) -> YouTubeScheduleInput:
        normalize_schedule(
            {
                "enabled": self.enabled,
                "run_at": self.run_at,
                "timezone": self.timezone,
                "weekdays": self.weekdays,
            },
            fallback=default_schedule(enabled=False, run_at="05:00"),
        )
        if self.enabled and not self.weekdays:
            raise ValueError("an enabled schedule must include at least one weekday")
        return self


class AssistantInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=20)
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    asset_class: str | None = None
    instrument_type: str | None = None
    venue_instrument_id: str | None = None


class EmbeddingConfigurationInput(BaseModel):
    connection_id: UUID
    model: str = Field(default=DEFAULT_MODEL, pattern=r"^text-embedding-3-(small|large)$")
    dimensions: int | None = Field(default=None, ge=64, le=3072)


def _document_data(payload: SourceInput, version: int = 1) -> dict:
    return build_source_data(
        name=payload.name,
        content=payload.content,
        media_type=payload.media_type,
        category=payload.category,
        tags=payload.tags,
        source_date=payload.source_date,
        version=version,
        source_kind=payload.source_kind,
        source_url=payload.source_url,
        external_id=payload.external_id,
        asset_class=payload.asset_class,
        instrument_type=payload.instrument_type,
        venue_instrument_id=payload.venue_instrument_id,
        specification_version_id=payload.specification_version_id,
        source_cut_refs=payload.source_cut_refs,
    )


def _extract_upload_text(filename: str, media_type: str, body: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "pdf" or media_type == "application/pdf":
        try:
            from pypdf import PdfReader

            pages = PdfReader(io.BytesIO(body)).pages
            return "\n\n".join(page.extract_text() or "" for page in pages).strip()
        except Exception as exc:  # noqa: BLE001 - map parser failures to safe validation error
            raise ValueError("unable to extract text from PDF") from exc
    if suffix == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)  # noqa: S314 - DOCX XML is parsed from a bounded upload
            return " ".join(
                value.text or "" for value in root.iter() if value.tag.endswith("}t")
            ).strip()
        except (KeyError, OSError, ValueError, ElementTree.ParseError) as exc:
            raise ValueError("unable to extract text from DOCX") from exc
    text = body.decode("utf-8", errors="replace")
    if suffix in {"vtt", "srt"}:
        text = re.sub(r"(?m)^\s*(?:WEBVTT|\d+|\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->.*)\s*$", "", text)
        text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        data = await embed_source_data(db, actor.owner_id, _document_data(payload))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    item = await ResourceStore(db).create(
        "knowledge_source",
        actor.owner_id,
        data,
        state="ACTIVE",
        actor_id=actor.actor_id,
        event_type="knowledge_ingestion.completed",
    )
    return item.public()


@router.post("/sources/upload", status_code=status.HTTP_201_CREATED)
async def upload_source(
    file: Annotated[UploadFile, File(...)],
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[str, Form()] = "general",
    tags: Annotated[str, Form()] = "",
):
    filename = file.filename or "uploaded-source"
    body = await file.read()
    media_type = file.content_type or "text/plain"
    try:
        validate_upload(filename, media_type, len(body))
        content = _extract_upload_text(filename, media_type, body)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    store = ResourceStore(db)
    duplicate = next(
        (
            item
            for item in await store.list("knowledge_source", actor.owner_id)
            if item.data.get("content_hash") == content_hash and item.state != "DELETED"
        ),
        None,
    )
    if duplicate is not None:
        return {**duplicate.public(), "duplicate": True}
    blob_key = f"knowledge/{content_hash}/{filename.replace('/', '_')}"
    LocalBlobStore(get_settings().blob_root).put(actor.owner_id, blob_key, body)
    payload = SourceInput(
        name=filename,
        content=content,
        media_type=media_type,
        category=category,
        tags=[value.strip() for value in tags.split(",") if value.strip()],
        source_kind="DOCUMENT_UPLOAD",
    )
    data = await embed_source_data(db, actor.owner_id, _document_data(payload))
    data["blob_key"] = blob_key
    item = await store.create(
        "knowledge_source",
        actor.owner_id,
        data,
        state="ACTIVE",
        actor_id=actor.actor_id,
        event_type="knowledge_upload.completed",
    )
    return item.public()


@router.get("/sources")
async def list_sources(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("knowledge_source", actor.owner_id)
    return [
        {key: value for key, value in item.public().items() if key != "segments"}
        for item in records
    ]


@router.post("/sources/{source_id}/reprocess")
async def reprocess_source(
    source_id: UUID,
    payload: SourceInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("knowledge_source", source_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "knowledge source not found")
    data = await embed_source_data(db, actor.owner_id, _document_data(payload, item.version + 1))
    updated = await store.update(
        item,
        data,
        state="ACTIVE",
        actor_id=actor.actor_id,
        event_type="knowledge_ingestion.completed",
    )
    return updated.public()


@router.post("/sources/{source_id}/disable")
async def disable_source(
    source_id: UUID,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("knowledge_source", source_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "knowledge source not found")
    updated = await store.update(
        item,
        state="DISABLED",
        actor_id=actor.actor_id,
        event_type="knowledge_source.disabled",
    )
    return updated.public()


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: UUID,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER))],
    _: Annotated[Actor, Depends(require_step_up("knowledge.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("knowledge_source", source_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "knowledge source not found")
    tombstone = {
        "name": item.data.get("name"),
        "content_hash": item.data.get("content_hash"),
        "deleted": True,
        "segments": [],
    }
    await store.update(
        item,
        tombstone,
        state="DELETED",
        actor_id=actor.actor_id,
        event_type="knowledge_source.deleted",
    )
    return {"deleted": True, "source_id": str(source_id)}


@router.post("/search")
async def search(
    payload: SearchInput,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    query_terms = set(re.findall(r"[a-z0-9]+", payload.query.lower()))
    query_vectors, _ = await embed_texts_for_owner(db, actor.owner_id, [payload.query])
    query_vector = query_vectors[0]

    def cosine(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=False))
        norm_left = math.sqrt(sum(value * value for value in left))
        norm_right = math.sqrt(sum(value * value for value in right))
        return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0

    hits: list[dict] = []
    for source in await ResourceStore(db).list("knowledge_source", actor.owner_id):
        if source.state != "ACTIVE":
            continue
        if payload.category and source.data.get("category") != payload.category:
            continue
        if payload.asset_class and source.data.get("asset_class") != payload.asset_class:
            continue
        if (
            payload.instrument_type
            and source.data.get("instrument_type") != payload.instrument_type
        ):
            continue
        if (
            payload.venue_instrument_id
            and source.data.get("venue_instrument_id") != payload.venue_instrument_id
        ):
            continue
        source_tags = set(source.data.get("tags", []))
        if payload.tags and not set(payload.tags).issubset(source_tags):
            continue
        source_date = source.data.get("source_date")
        if payload.source_date_from and source_date and source_date < payload.source_date_from:
            continue
        if payload.source_date_to and source_date and source_date > payload.source_date_to:
            continue
        for segment in source.data.get("segments", []):
            terms = set(re.findall(r"[a-z0-9]+", segment["text"].lower()))
            overlap = len(query_terms & terms)
            lexical_score = overlap / max(len(query_terms), 1)
            vector_score = max(0.0, cosine(query_vector, segment.get("embedding", [])))
            if not overlap and vector_score < 0.08:
                continue
            score = (0.65 * lexical_score) + (0.35 * vector_score)
            hits.append(
                {
                    "source_id": str(source.id),
                    "source_name": source.data.get("name"),
                    "document_id": segment["document_id"],
                    "segment_id": segment["id"],
                    "segment_ordinal": segment["ordinal"],
                    "source_version": source.version,
                    "source_date": source_date,
                    "score": score,
                    "lexical_score": lexical_score,
                    "vector_score": vector_score,
                    "embedding_model": source.data.get("embedding_model"),
                    "text": segment["text"],
                }
            )
    hits.sort(key=lambda hit: (-hit["score"], hit["source_name"], hit["segment_ordinal"]))
    hits, reranking = await rerank_for_owner(db, actor.owner_id, payload.query, hits, payload.limit)
    audit = await ResourceStore(db).audit(
        actor.owner_id,
        actor.actor_id,
        "knowledge.retrieved",
        "knowledge_search",
        None,
        {
            "query_hash": hashlib.sha256(payload.query.encode()).hexdigest(),
            "result_segment_ids": [hit["segment_id"] for hit in hits],
            "reranking": reranking,
        },
    )
    return {
        "authority": "CONTEXT_ONLY",
        "may_replace_facts": False,
        "retrieval_audit_id": str(audit.id),
        "citations": hits,
        "reranking": reranking,
    }


@router.post("/assistant")
async def assistant(
    payload: AssistantInput,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Answer from owner-scoped evidence; this endpoint cannot create execution commands."""
    result = await search(
        SearchInput(
            query=payload.question,
            limit=payload.limit,
            category=payload.category,
            tags=payload.tags,
            asset_class=payload.asset_class,
            instrument_type=payload.instrument_type,
            venue_instrument_id=payload.venue_instrument_id,
        ),
        actor,
        db,
    )
    retrieval_hits = [
        RetrievalHit(
            segment_id=UUID(item["segment_id"]),
            document_id=UUID(item["document_id"]),
            source_id=UUID(item["source_id"]),
            score=float(item["score"]),
            text=item["text"],
            provenance={
                "source_name": str(item.get("source_name", "")),
                "source_version": str(item.get("source_version", "")),
                "segment": str(item.get("segment_ordinal", "")),
            },
        )
        for item in result["citations"]
    ]
    active_trade = bool(await ResourceStore(db).list("active_trade", actor.owner_id))
    answer = KnowledgeAssistant().answer(
        KnowledgeQuestion(
            owner_id=actor.owner_id, question=payload.question, active_trade=active_trade
        ),
        retrieval_hits,
        degraded=result["reranking"]["status"] == "DEGRADED",
    )
    return answer.model_dump(mode="json") | {
        "authority": result["authority"],
        "retrieval_audit_id": result["retrieval_audit_id"],
        "reranking": result["reranking"],
    }


@router.get("/reranking-configuration")
async def get_reranking_configuration(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("knowledge_reranking_configuration", actor.owner_id)
    if not records:
        return {
            "configured": False,
            "provider": "COHERE",
            "connection_id": None,
            "model": COHERE_MODEL,
            "candidate_limit": 50,
            "verified_at": None,
        }
    return {"configured": True, **records[0].data}


@router.put("/reranking-configuration")
async def save_reranking_configuration(
    payload: RerankingConfigurationInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        connection = await resolve_connection(db, actor.owner_id, payload.connection_id)
        if connection.profile.provider != ConnectionProvider.COHERE or not connection.secret:
            raise ValueError("invalid reranking connection")
    except (LookupError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Select an active Cohere connection with an encrypted API key belonging to this owner.",
        ) from exc
    try:
        await cohere_rerank(
            connection.secret,
            "What is knowledge retrieval?",
            ["Knowledge retrieval finds relevant evidence for a question."],
            model=payload.model,
            top_n=1,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Cohere verification failed. Check the API key, model access and availability.",
        ) from exc
    store = ResourceStore(db)
    records = await store.list("knowledge_reranking_configuration", actor.owner_id)
    data = {
        **payload.model_dump(mode="json"),
        "provider": "COHERE",
        "verified_at": datetime.now(UTC).isoformat(),
    }
    if records:
        record = await store.update(
            records[0],
            data,
            actor_id=actor.actor_id,
            event_type="knowledge_reranking.configuration_replaced",
        )
    else:
        record = await store.create(
            "knowledge_reranking_configuration",
            actor.owner_id,
            data,
            actor_id=actor.actor_id,
            event_type="knowledge_reranking.configuration_saved",
        )
    return {"configured": True, **record.data}


@router.delete("/reranking-configuration")
async def disable_reranking(
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    for record in await store.list("knowledge_reranking_configuration", actor.owner_id):
        await store.update(
            record,
            state="DELETED",
            actor_id=actor.actor_id,
            event_type="knowledge_reranking.disabled",
        )
    return await get_reranking_configuration(actor, db)


@router.post("/youtube/scrape")
async def scrape_youtube(
    payload: YouTubeScrapeInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    requested_at = datetime.now(UTC).isoformat()
    run = await store.create(
        "youtube_discovery_run",
        actor.owner_id,
        {
            **payload.model_dump(mode="json"),
            "trigger": "MANUAL",
            "provider": "SERPAPI",
            "provider_requested_at": requested_at,
        },
        state="RUNNING",
        actor_id=actor.actor_id,
        event_type="knowledge_youtube_discovery.requested",
    )
    try:
        result = await ingest_youtube_discovery(
            db,
            actor.owner_id,
            **payload.model_dump(mode="json"),
            actor_id=actor.actor_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    completed_at = datetime.now(UTC).isoformat()
    await store.update(
        run,
        {**run.data, **result, "completed_at": completed_at},
        state="SUCCEEDED",
        actor_id=actor.actor_id,
        event_type="knowledge_youtube_discovery.completed",
    )
    return {
        **result,
        "run_id": str(run.id),
        "trigger": "MANUAL",
        "provider": "SERPAPI",
        "provider_requested_at": requested_at,
        "completed_at": completed_at,
    }


@router.get("/youtube/schedule")
async def get_youtube_schedule(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("youtube_discovery_schedule", actor.owner_id)
    record = next(iter(records), None)
    if record is None or record.state == "DELETED":
        schedule = default_schedule(enabled=False, run_at="05:00")
        return {
            "configured": False,
            **schedule,
            "query": "trading strategy",
            "limit": 5,
            "languages": ["en"],
            "category": "trading",
            "next_run_at": None,
            "saved_at": None,
        }
    schedule = normalize_schedule(
        record.data, fallback=default_schedule(enabled=False, run_at="05:00")
    )
    upcoming = next_run_at(schedule)
    return {
        **record.public(),
        **schedule,
        "configured": True,
        "next_run_at": upcoming.isoformat() if upcoming else None,
        "saved_at": record.updated_at,
    }


@router.put("/youtube/schedule")
async def save_youtube_schedule(
    payload: YouTubeScheduleInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    existing = next(iter(await store.list("youtube_discovery_schedule", actor.owner_id)), None)
    data = payload.model_dump(mode="json")
    if existing is None or existing.state == "DELETED":
        record = await store.create(
            "youtube_discovery_schedule",
            actor.owner_id,
            data,
            actor_id=actor.actor_id,
            event_type="knowledge_youtube_schedule.saved",
        )
    else:
        record = await store.update(
            existing,
            data,
            state="ACTIVE",
            actor_id=actor.actor_id,
            event_type="knowledge_youtube_schedule.replaced",
        )
    schedule = normalize_schedule(data, fallback=default_schedule(enabled=False, run_at="05:00"))
    upcoming = next_run_at(schedule)
    return {
        **record.public(),
        **schedule,
        "configured": True,
        "next_run_at": upcoming.isoformat() if upcoming else None,
        "saved_at": record.updated_at,
    }


@router.delete("/youtube/schedule")
async def delete_youtube_schedule(
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    record = next(iter(await store.list("youtube_discovery_schedule", actor.owner_id)), None)
    if record is not None:
        await store.update(
            record,
            {**record.data, "enabled": False, "removed_at": datetime.now(UTC).isoformat()},
            state="DELETED",
            actor_id=actor.actor_id,
            event_type="knowledge_youtube_schedule.removed",
        )
    return {
        "configured": False,
        **default_schedule(enabled=False, run_at="05:00"),
        "query": "trading strategy",
        "limit": 5,
        "languages": ["en"],
        "category": "trading",
        "next_run_at": None,
        "saved_at": None,
    }


@router.get("/youtube/runs")
async def list_youtube_runs(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [
        item.public()
        for item in await ResourceStore(db).list("youtube_discovery_run", actor.owner_id)
    ][:20]


@router.get("/embedding-configuration")
async def get_embedding_configuration(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("knowledge_embedding_configuration", actor.owner_id)
    if not records:
        return {
            "configured": False,
            "provider": "LOCAL_FALLBACK",
            "model": "deterministic-hash-v1",
            "dimensions": 64,
            "connection_id": None,
            "verified_at": None,
        }
    return {"configured": True, **records[0].data}


async def _verify_and_reindex_embedding_configuration(
    payload: EmbeddingConfigurationInput,
    actor: Actor,
    db: AsyncSession,
) -> dict:
    try:
        connection = await resolve_connection(db, actor.owner_id, payload.connection_id)
    except (LookupError, RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if connection.profile.provider != ConnectionProvider.OPENAI or not connection.secret:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "select an active OpenAI connection with an encrypted API key",
        )
    if payload.model.endswith("small") and payload.dimensions and payload.dimensions > 1536:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "text-embedding-3-small supports at most 1536 dimensions",
        )
    try:
        test_vector = (
            await openai_embeddings(
                connection.secret,
                ["Matrades knowledge embedding verification"],
                model=payload.model,
                dimensions=payload.dimensions,
            )
        )[0]
        store = ResourceStore(db)
        sources = await store.list("knowledge_source", actor.owner_id)
        reindexed_segments = 0
        for source in sources:
            segments = [dict(item) for item in source.data.get("segments", [])]
            if not segments:
                continue
            vectors = await openai_embeddings(
                connection.secret,
                [str(item["text"]) for item in segments],
                model=payload.model,
                dimensions=payload.dimensions,
            )
            for segment, vector in zip(segments, vectors, strict=True):
                segment["embedding"] = vector
            await store.update(
                source,
                {
                    **source.data,
                    "segments": segments,
                    "embedding_model": payload.model,
                    "embedding_dimensions": len(vectors[0]),
                },
                actor_id=actor.actor_id,
                event_type="knowledge_embedding.reindexed",
            )
            reindexed_segments += len(segments)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "provider": "OPENAI",
        "connection_id": str(payload.connection_id),
        "model": payload.model,
        "dimensions": len(test_vector),
        "verified_at": datetime.now(UTC).isoformat(),
        "reindexed_segments": reindexed_segments,
    }


async def _activate_embedding_configuration(
    payload: EmbeddingConfigurationInput,
    actor: Actor,
    db: AsyncSession,
    *,
    restored_from_version: int | None = None,
) -> dict:
    configuration = await _verify_and_reindex_embedding_configuration(payload, actor, db)
    store = ResourceStore(db)
    records = await store.list("knowledge_embedding_configuration", actor.owner_id)
    current_version = int(records[0].data.get("configuration_version", 0)) if records else 0
    configuration = {
        **configuration,
        "configuration_version": current_version + 1,
        "restored_from_version": restored_from_version,
    }
    if records:
        record = await store.update(
            records[0],
            configuration,
            actor_id=actor.actor_id,
            event_type="knowledge_embedding.configuration_replaced",
        )
    else:
        record = await store.create(
            "knowledge_embedding_configuration",
            actor.owner_id,
            configuration,
            actor_id=actor.actor_id,
            event_type="knowledge_embedding.configuration_saved",
        )
    await store.create(
        "knowledge_embedding_configuration_version",
        actor.owner_id,
        configuration,
        actor_id=actor.actor_id,
        event_type="knowledge_embedding.version_created",
    )
    return {"configured": True, **record.data}


@router.put("/embedding-configuration")
async def save_embedding_configuration(
    payload: EmbeddingConfigurationInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _activate_embedding_configuration(payload, actor, db)


@router.get("/embedding-configuration/versions")
async def list_embedding_configuration_versions(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list(
        "knowledge_embedding_configuration_version", actor.owner_id
    )
    return [item.public() for item in records]


@router.post("/embedding-configuration/versions/{configuration_version}/restore")
async def restore_embedding_configuration_version(
    configuration_version: int,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list(
        "knowledge_embedding_configuration_version", actor.owner_id
    )
    version = next(
        (
            item
            for item in records
            if int(item.data.get("configuration_version", 0)) == configuration_version
        ),
        None,
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "embedding configuration version not found")
    return await _activate_embedding_configuration(
        EmbeddingConfigurationInput(
            connection_id=UUID(str(version.data["connection_id"])),
            model=str(version.data["model"]),
            dimensions=int(version.data["dimensions"]),
        ),
        actor,
        db,
        restored_from_version=configuration_version,
    )


@assistant_router.post("/answers")
async def assistant_answer(
    payload: AssistantInput,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Contract-compatible alias for the read-only knowledge answer endpoint."""
    return await assistant(payload, actor, db)


@router.get("/health")
async def health(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sources = await ResourceStore(db).list("knowledge_source", actor.owner_id)
    pgvector_available = bool(
        await db.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
    )
    embedding_configurations = await ResourceStore(db).list(
        "knowledge_embedding_configuration", actor.owner_id
    )
    embedding_configuration = embedding_configurations[0].data if embedding_configurations else None
    return {
        "state": "HEALTHY",
        "authoritative": False,
        "active_sources": len(sources),
        "indexed_segments": sum(int(item.data.get("segment_count", 0)) for item in sources),
        "pgvector_available": pgvector_available,
        "vector_storage": "RESOURCE_JSON",
        "embedding_model": (
            embedding_configuration.get("model")
            if embedding_configuration
            else "deterministic-hash-v1"
        ),
        "capabilities": [
            "lexical",
            "vector_hybrid",
            "owner_scope",
            "metadata_filters",
            "provenance",
            "document_upload",
            "youtube_transcripts",
        ],
    }
