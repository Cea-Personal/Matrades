from __future__ import annotations

import shutil
from collections import defaultdict
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db
from modules.identity.authorization import Actor
from packages.shared.config import get_settings
from packages.shared.store import AuditRecord, ResourceStore

router = APIRouter(prefix="/operations", tags=["Operations"])


class NotificationPreferences(BaseModel):
    in_app: bool = True
    browser_push: bool = False
    email: bool = False
    telegram: bool = False
    urgent_only_external: bool = True


@router.get("/health")
async def health(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    components: list[dict[str, Any]] = []
    try:
        await db.execute(text("SELECT 1"))
        components.append({"component": "database", "state": "HEALTHY", "fresh": True})
    except Exception as exc:  # noqa: BLE001 - health maps dependency errors to public state
        components.append(
            {"component": "database", "state": "OFFLINE", "fresh": False, "error": str(exc)}
        )
    codex_available = shutil.which(get_settings().codex_binary) is not None
    components.append(
        {
            "component": "codex_app_server",
            "state": "HEALTHY" if codex_available else "OFFLINE",
            "fresh": codex_available,
            "runtime": "CODEX_APP_SERVER",
        }
    )
    connections = await ResourceStore(db).list("connection", actor.owner_id)
    components.extend(
        {
            "component": f"connection:{item.data.get('name', item.id)}",
            "state": item.data.get("health", "UNTESTED"),
            "fresh": item.data.get("health") == "HEALTHY",
            "last_success": item.data.get("last_success"),
            "latency_ms": item.data.get("latency_ms"),
        }
        for item in connections
    )
    states = {item["state"] for item in components}
    overall = (
        "OFFLINE"
        if "OFFLINE" in states
        else "DEGRADED"
        if states - {"HEALTHY"}
        else "HEALTHY"
    )
    return {"state": overall, "components": components}


@router.get("/approvals")
async def approvals(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    hil1 = [
        item.public()
        for item in await store.list("research_run", actor.owner_id)
        if item.state == "READY"
    ]
    hil2 = [
        item.public()
        for item in await store.list("trade_proposal", actor.owner_id)
        if item.state == "AWAITING_HIL2"
    ]
    hil3 = [
        item.public()
        for item in await store.list("management_recommendation", actor.owner_id)
        if item.state == "ACTION_REQUIRED"
    ]
    return {"HIL-1": hil1, "HIL-2": hil2, "HIL-3": hil3}


@router.get("/journal/{aggregate_id}")
async def journal(
    aggregate_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    events = list(
        (
            await db.scalars(
                select(AuditRecord)
                .where(
                    AuditRecord.owner_id == actor.owner_id,
                    AuditRecord.aggregate_id == aggregate_id,
                )
                .order_by(AuditRecord.created_at)
            )
        ).all()
    )
    proposal = await ResourceStore(db).get("trade_proposal", aggregate_id, actor.owner_id)
    return {
        "aggregate_id": str(aggregate_id),
        "proposal": proposal.public() if proposal else None,
        "events": [item.public() for item in events],
        "reconstructable": bool(events),
    }


@router.get("/performance")
async def performance(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    dimension: str = "strategy_version",
):
    groups: dict[str, list[Decimal]] = defaultdict(list)
    for trade in await ResourceStore(db).list("active_trade", actor.owner_id):
        position = trade.data.get("broker_position", {})
        key = str(trade.data.get(dimension) or position.get(dimension) or "unattributed")
        net = Decimal(str(position.get("pnl", 0))) - Decimal(
            str(position.get("fees", 0))
        )
        groups[key].append(net)
    result = {
        key: {
            "trade_count": len(values),
            "net_pnl": str(sum(values, Decimal("0"))),
            "expectancy": str(sum(values, Decimal("0")) / len(values)),
            "win_rate": sum(1 for value in values if value > 0) / len(values),
        }
        for key, values in groups.items()
    }
    return {"dimension": dimension, "groups": result}


@router.get("/audit")
async def audit(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 100,
):
    records = list(
        (
            await db.scalars(
                select(AuditRecord)
                .where(AuditRecord.owner_id == actor.owner_id)
                .order_by(AuditRecord.created_at.desc())
                .limit(min(max(limit, 1), 500))
            )
        ).all()
    )
    return [item.public() for item in records]


@router.get("/notifications")
async def notifications(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("notification", actor.owner_id)
    return [item.public() for item in records]


@router.post("/notifications/preferences")
async def save_notification_preferences(
    payload: NotificationPreferences,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    existing = await store.list("notification_preferences", actor.owner_id)
    if existing:
        item = await store.update(
            existing[0],
            payload.model_dump(),
            actor_id=actor.actor_id,
            event_type="notification.preferences_changed",
        )
    else:
        item = await store.create(
            "notification_preferences",
            actor.owner_id,
            payload.model_dump(),
            actor_id=actor.actor_id,
        )
    return item.public()


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("notification", notification_id, actor.owner_id)
    if item is None:
        raise HTTPException(404, "notification not found")
    return (
        await store.update(item, {**item.data, "read": True}, actor_id=actor.actor_id)
    ).public()
