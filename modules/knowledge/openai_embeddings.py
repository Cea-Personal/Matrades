"""Owner-scoped OpenAI embedding configuration and API adapter."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from modules.connections.models import ConnectionProvider
from modules.connections.resolution import resolve_connection
from modules.knowledge.ingestion import token_embedding
from packages.shared.store import ResourceStore


DEFAULT_MODEL = "text-embedding-3-small"


async def openai_embeddings(
    api_key: str,
    texts: list[str],
    *,
    model: str = DEFAULT_MODEL,
    dimensions: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[list[float]]:
    if not texts or any(not value.strip() for value in texts):
        raise ValueError("embedding input must contain non-empty text")
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=30, headers={"User-Agent": "Matrades/1"})
    payload: dict[str, Any] = {"model": model, "input": texts, "encoding_format": "float"}
    if dimensions is not None:
        payload["dimensions"] = dimensions
    try:
        response = await http.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        if response.is_error:
            try:
                detail = str(response.json().get("error", {}).get("message", ""))
            except ValueError:
                detail = ""
            raise RuntimeError(
                f"OpenAI embedding request failed ({response.status_code})"
                + (f": {detail[:180]}" if detail else "")
            )
        body = response.json()
        ordered = sorted(body.get("data", []), key=lambda item: int(item["index"]))
        vectors = [[float(value) for value in item["embedding"]] for item in ordered]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise RuntimeError("OpenAI returned an incomplete embedding response")
        return vectors
    finally:
        if owns_client:
            await http.aclose()


async def get_embedding_configuration(session: AsyncSession, owner_id: UUID) -> dict[str, Any] | None:
    records = await ResourceStore(session).list("knowledge_embedding_configuration", owner_id)
    return records[0].data if records else None


async def embed_texts_for_owner(
    session: AsyncSession, owner_id: UUID, texts: list[str]
) -> tuple[list[list[float]], str]:
    configuration = await get_embedding_configuration(session, owner_id)
    if configuration is None:
        return [token_embedding(value) for value in texts], "deterministic-hash-v1"
    connection = await resolve_connection(
        session, owner_id, UUID(str(configuration["connection_id"]))
    )
    if connection.profile.provider != ConnectionProvider.OPENAI or not connection.secret:
        raise RuntimeError("configured knowledge embedding connection is not an active OpenAI connection")
    model = str(configuration.get("model") or DEFAULT_MODEL)
    dimensions = configuration.get("dimensions")
    vectors = await openai_embeddings(
        connection.secret,
        texts,
        model=model,
        dimensions=int(dimensions) if dimensions else None,
    )
    return vectors, model


async def embed_source_data(
    session: AsyncSession, owner_id: UUID, data: dict[str, Any]
) -> dict[str, Any]:
    segments = [dict(item) for item in data.get("segments", [])]
    if not segments:
        return data
    vectors, model = await embed_texts_for_owner(
        session, owner_id, [str(item["text"]) for item in segments]
    )
    for segment, vector in zip(segments, vectors, strict=True):
        segment["embedding"] = vector
    return {
        **data,
        "segments": segments,
        "embedding_model": model,
        "embedding_dimensions": len(vectors[0]),
    }
