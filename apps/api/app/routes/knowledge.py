from __future__ import annotations

import hashlib
import io
import math
import re
import zipfile
from typing import Annotated
from uuid import UUID
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.blob_store.local import LocalBlobStore
from apps.api.app.dependencies import current_actor, get_db, require_roles, require_step_up
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import find_connection
from modules.identity.authorization import Actor, Role
from modules.knowledge.ingestion import build_source_data, token_embedding
from modules.knowledge.youtube import scrape_youtube_transcripts
from modules.security.platform import validate_upload
from packages.shared.config import get_settings
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


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
    query: str = Field(min_length=1)
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
        data = _document_data(payload)
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
    data = _document_data(payload)
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
    data = _document_data(payload, item.version + 1)
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
    query_vector = token_embedding(payload.query)

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
    hits = hits[: payload.limit]
    audit = await ResourceStore(db).audit(
        actor.owner_id,
        actor.actor_id,
        "knowledge.retrieved",
        "knowledge_search",
        None,
        {
            "query_hash": hashlib.sha256(payload.query.encode()).hexdigest(),
            "result_segment_ids": [hit["segment_id"] for hit in hits],
        },
    )
    return {
        "authority": "CONTEXT_ONLY",
        "may_replace_facts": False,
        "retrieval_audit_id": str(audit.id),
        "citations": hits,
    }


@router.post("/youtube/scrape")
async def scrape_youtube(
    payload: YouTubeScrapeInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    connection = await find_connection(db, actor.owner_id, ConnectionProvider.SERPAPI)
    if connection is None or not connection.secret:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "configure an active SerpApi connection first"
        )
    store = ResourceStore(db)
    existing = await store.list("knowledge_source", actor.owner_id)
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
        payload.query,
        limit=payload.limit,
        languages=payload.languages,
        skip_video_ids=existing_ids,
    )
    created: list[dict] = []
    skipped = 0
    failed: list[dict] = []
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
        source = SourceInput(
            name=video.title,
            content=content,
            media_type="text/plain",
            category=payload.category,
            tags=["youtube", "transcript", "trading"],
            source_kind="YOUTUBE_TRANSCRIPT",
            source_url=video.url,
            external_id=video.video_id,
        )
        data = _document_data(source)
        item = await store.create(
            "knowledge_source",
            actor.owner_id,
            data,
            state="ACTIVE",
            actor_id=actor.actor_id,
            event_type="knowledge_youtube_ingestion.completed",
        )
        created.append(item.public())
        existing_ids.add(video.video_id)
        existing_hashes.add(content_hash)
    return {
        "query": payload.query,
        "discovered": len(results),
        "created": len(created),
        "skipped": skipped,
        "failed": failed,
        "sources": [
            {key: value for key, value in item.items() if key != "segments"} for item in created
        ],
    }


@router.get("/health")
async def health(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sources = await ResourceStore(db).list("knowledge_source", actor.owner_id)
    return {
        "state": "HEALTHY",
        "authoritative": False,
        "active_sources": len(sources),
        "indexed_segments": sum(int(item.data.get("segment_count", 0)) for item in sources),
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
