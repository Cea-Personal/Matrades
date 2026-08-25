from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db
from modules.identity.authorization import Actor
from packages.shared.store import AuditRecord

router = APIRouter(prefix="/events", tags=["Events"])


async def event_stream(owner_id: UUID, db: AsyncSession) -> AsyncIterator[str]:
    """Owner-scoped projection transport; records remain authoritative over SSE."""
    seen: set[UUID] = set()
    while True:
        records = list(
            (
                await db.scalars(
                    select(AuditRecord)
                    .where(AuditRecord.owner_id == owner_id)
                    .order_by(AuditRecord.created_at.desc())
                    .limit(50)
                )
            ).all()
        )
        for item in reversed(records):
            if item.id in seen:
                continue
            seen.add(item.id)
            yield (f"event: domain\ndata: {json.dumps(item.public(), default=str)}\n\n")
        yield f"event: heartbeat\ndata: {json.dumps({'authoritative': False})}\n\n"
        await asyncio.sleep(5)


@router.get("")
async def events(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    return StreamingResponse(
        event_stream(actor.owner_id, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
