from __future__ import annotations

import hashlib
import re
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from modules.identity.authorization import Actor, Role
from modules.knowledge.ingestion import chunk
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


class SourceInput(BaseModel):
    name: str
    content: str = Field(min_length=1)
    media_type: str = "text/plain"
    category: str = "general"
    tags: list[str] = []
    source_date: str | None = None


class SearchInput(BaseModel):
    query: str = Field(min_length=1)
    category: str | None = None
    tags: list[str] = []
    source_date_from: str | None = None
    source_date_to: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


def _document_data(payload: SourceInput, version: int = 1) -> dict:
    document_id = uuid4()
    content_hash = hashlib.sha256(payload.content.encode()).hexdigest()
    segments = [
        {
            "id": str(uuid4()),
            "document_id": str(document_id),
            "ordinal": ordinal,
            "text": text,
            "version": version,
        }
        for ordinal, text in enumerate(chunk(payload.content))
    ]
    return {
        "name": payload.name,
        "media_type": payload.media_type,
        "category": payload.category,
        "tags": payload.tags,
        "source_date": payload.source_date,
        "document_id": str(document_id),
        "content_hash": content_hash,
        "generation": version,
        "segments": segments,
        "ingestion_state": "INDEXED",
        "segment_count": len(segments),
    }


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await ResourceStore(db).create(
        "knowledge_source",
        actor.owner_id,
        _document_data(payload),
        state="ACTIVE",
        actor_id=actor.actor_id,
        event_type="knowledge_ingestion.completed",
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
    hits: list[dict] = []
    for source in await ResourceStore(db).list("knowledge_source", actor.owner_id):
        if source.state != "ACTIVE":
            continue
        if payload.category and source.data.get("category") != payload.category:
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
            if not overlap:
                continue
            score = overlap / max(len(query_terms), 1)
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


@router.get("/health")
async def health(_: Annotated[Actor, Depends(current_actor)]):
    return {
        "state": "HEALTHY",
        "authoritative": False,
        "capabilities": ["lexical", "owner_scope", "metadata_filters", "provenance"],
    }
