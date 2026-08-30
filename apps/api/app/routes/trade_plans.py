from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db
from modules.identity.authorization import Actor
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/trade-plans", tags=["Trade Plans"])


@router.get("")
async def list_trade_plans(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [item.public() for item in await ResourceStore(db).list("trade_plan", actor.owner_id)]


@router.get("/{plan_id}")
async def get_trade_plan(
    plan_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await ResourceStore(db).get("trade_plan", plan_id, actor.owner_id)
    if item is None:
        raise HTTPException(status_code=404, detail="trade plan not found")
    return item.public()
