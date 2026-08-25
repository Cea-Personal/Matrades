from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles, require_step_up
from apps.worker.app.tasks.operations import deliver_notification
from modules.credentials.vault import EnvelopeCipher
from modules.identity.authorization import Actor, Role
from modules.notifications.providers import send_notification
from packages.shared.config import get_settings
from packages.shared.runtime_health import CODEX_APP_SERVER_HEARTBEAT_KEY
from packages.shared.store import AuditRecord, ResourceStore

router = APIRouter(prefix="/operations", tags=["Operations"])


class NotificationPreferences(BaseModel):
    in_app: bool = True
    browser_push: bool = False
    email: bool = False
    telegram: bool = False
    pushover: bool = False
    urgent_only_external: bool = True


class NotificationChannelInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["TELEGRAM", "PUSHOVER"]
    secret: str = Field(min_length=1, max_length=512)
    destination: str = Field(min_length=1, max_length=256)
    enabled: bool = True


class NotificationChannelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    secret: str | None = Field(default=None, min_length=1, max_length=512)
    destination: str | None = Field(default=None, min_length=1, max_length=256)
    enabled: bool | None = None


class NotificationInput(BaseModel):
    kind: str = Field(default="system", min_length=1, max_length=80)
    urgency: str = Field(default="NORMAL", min_length=1, max_length=24)
    title: str = Field(min_length=1, max_length=240)
    message: str = Field(min_length=1, max_length=4000)
    dedupe_key: str | None = Field(default=None, max_length=240)


async def codex_app_server_health() -> dict[str, Any]:
    settings = get_settings()
    if not settings.codex_enabled:
        return {
            "component": "codex_app_server",
            "state": "DISABLED",
            "fresh": False,
            "runtime": "CODEX_APP_SERVER",
        }
    redis = Redis.from_url(settings.redis_url)
    started = monotonic()
    try:
        heartbeat = await redis.get(CODEX_APP_SERVER_HEARTBEAT_KEY)
    except RedisError as exc:
        return {
            "component": "codex_app_server",
            "state": "OFFLINE",
            "fresh": False,
            "runtime": "CODEX_APP_SERVER",
            "error": f"heartbeat unavailable: {type(exc).__name__}",
        }
    finally:
        await redis.aclose()
    healthy = heartbeat == b"healthy"
    return {
        "component": "codex_app_server",
        "state": "HEALTHY" if healthy else "OFFLINE",
        "fresh": healthy,
        "runtime": "CODEX_APP_SERVER",
        "latency_ms": int((monotonic() - started) * 1000),
    }


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
    components.append(await codex_app_server_health())
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
        "OFFLINE" if "OFFLINE" in states else "DEGRADED" if states - {"HEALTHY"} else "HEALTHY"
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
        net = Decimal(str(position.get("pnl", 0))) - Decimal(str(position.get("fees", 0)))
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


@router.post("/notifications", status_code=202)
async def create_notification(
    payload: NotificationInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    store = ResourceStore(db)
    if payload.dedupe_key:
        existing = [
            item
            for item in await store.list("notification", actor.owner_id)
            if item.data.get("dedupe_key") == payload.dedupe_key
        ]
        if existing:
            return existing[0].public()
    item = await store.create(
        "notification",
        actor.owner_id,
        payload.model_dump(mode="json"),
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="notification.queued",
    )
    await db.commit()
    deliver_notification.apply_async(args=[str(item.id)], countdown=1)
    return item.public()


def _notification_cipher() -> EnvelopeCipher:
    return EnvelopeCipher(get_settings().secret_key.get_secret_value().encode())


def _public_channel(record, credential=None) -> dict[str, Any]:
    data = record.public()
    data.pop("secret", None)
    data.pop("envelope", None)
    if credential is not None:
        data["masked_suffix"] = credential.data.get("masked_suffix")
        data["credential_status"] = credential.data.get("status", "UNTESTED")
    return data


@router.get("/notifications/preferences")
async def notification_preferences(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    existing = await ResourceStore(db).list("notification_preferences", actor.owner_id)
    return existing[0].public() if existing else NotificationPreferences().model_dump()


@router.get("/notification-channels")
async def notification_channels(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    store = ResourceStore(db)
    credentials = {str(item.id): item for item in await store.list("credential", actor.owner_id)}
    return [
        _public_channel(item, credentials.get(str(item.data.get("credential_id"))))
        for item in await store.list("notification_channel", actor.owner_id)
    ]


@router.post("/notification-channels", status_code=201)
async def create_notification_channel(
    payload: NotificationChannelInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    store = ResourceStore(db)
    envelope = _notification_cipher().encrypt(actor.owner_id, payload.secret)
    credential = await store.create(
        "credential",
        actor.owner_id,
        {
            "name": f"{payload.name} secret",
            "provider": payload.provider,
            "purpose": "notification",
            "masked_suffix": f"••••{payload.secret[-4:]}",
            "status": "UNTESTED",
            "key_version": envelope.key_version,
            "envelope": envelope.as_dict(),
        },
        actor_id=actor.actor_id,
        event_type="notification.credential_created",
    )
    channel = await store.create(
        "notification_channel",
        actor.owner_id,
        {
            "name": payload.name,
            "provider": payload.provider,
            "credential_id": str(credential.id),
            "destination": payload.destination,
            "enabled": payload.enabled,
            "health": "UNTESTED",
            "last_tested": None,
            "last_error": None,
        },
        state="ACTIVE" if payload.enabled else "DISABLED",
        actor_id=actor.actor_id,
        event_type="notification.channel_created",
    )
    return _public_channel(channel, credential)


@router.patch("/notification-channels/{channel_id}")
async def update_notification_channel(
    channel_id: UUID,
    payload: NotificationChannelPatch,
    actor: Annotated[Actor, Depends(require_step_up("notification.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    store = ResourceStore(db)
    channel = await store.get("notification_channel", channel_id, actor.owner_id)
    if channel is None:
        raise HTTPException(404, "notification channel not found")
    data = {**channel.data}
    for field in ("name", "destination"):
        value = getattr(payload, field)
        if value is not None:
            data[field] = value
    if payload.enabled is not None:
        data["enabled"] = payload.enabled
    credential = await store.get("credential", UUID(str(data["credential_id"])), actor.owner_id)
    if credential is None:
        raise HTTPException(409, "notification credential unavailable")
    if payload.secret is not None:
        envelope = _notification_cipher().encrypt(actor.owner_id, payload.secret)
        await store.update(
            credential,
            {
                **credential.data,
                "masked_suffix": f"••••{payload.secret[-4:]}",
                "status": "UNTESTED",
                "key_version": envelope.key_version,
                "envelope": envelope.as_dict(),
            },
            actor_id=actor.actor_id,
            event_type="notification.credential_replaced",
        )
        data.update({"health": "UNTESTED", "last_tested": None, "last_error": None})
    updated = await store.update(
        channel,
        data,
        state="ACTIVE" if data.get("enabled", True) else "DISABLED",
        actor_id=actor.actor_id,
        event_type="notification.channel_updated",
    )
    return _public_channel(updated, credential)


@router.delete("/notification-channels/{channel_id}")
async def delete_notification_channel(
    channel_id: UUID,
    actor: Annotated[Actor, Depends(require_step_up("notification.change"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    store = ResourceStore(db)
    channel = await store.get("notification_channel", channel_id, actor.owner_id)
    if channel is None:
        raise HTTPException(404, "notification channel not found")
    credential = await store.get(
        "credential", UUID(str(channel.data["credential_id"])), actor.owner_id
    )
    updated = await store.update(
        channel,
        {**channel.data, "enabled": False, "deleted_at": datetime.now(UTC).isoformat()},
        state="DELETED",
        actor_id=actor.actor_id,
        event_type="notification.channel_deleted",
    )
    if credential is not None:
        await store.update(
            credential,
            {**credential.data, "status": "RETIRED", "retired_at": datetime.now(UTC).isoformat()},
            state="DELETED",
            actor_id=actor.actor_id,
            event_type="notification.credential_retired",
        )
    return updated.public()


@router.post("/notification-channels/{channel_id}/test")
async def test_notification_channel(
    channel_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    store = ResourceStore(db)
    channel = await store.get("notification_channel", channel_id, actor.owner_id)
    if channel is None:
        raise HTTPException(404, "notification channel not found")
    credential = await store.get(
        "credential", UUID(str(channel.data["credential_id"])), actor.owner_id
    )
    if credential is None:
        raise HTTPException(409, "notification credential unavailable")
    try:
        secret = _notification_cipher().decrypt(actor.owner_id, credential.data["envelope"])
        receipt = await send_notification(
            str(channel.data["provider"]),
            secret,
            str(channel.data["destination"]),
            title="Matrades test notification",
            message="This channel is configured and reachable.",
        )
    except Exception as exc:  # noqa: BLE001 - provider and vault failures map to safe health state
        await store.update(
            channel,
            {
                **channel.data,
                "health": "OFFLINE",
                "last_tested": datetime.now(UTC).isoformat(),
                "last_error": str(exc)[:200],
            },
            actor_id=actor.actor_id,
            event_type="notification.channel_test_failed",
        )
        raise HTTPException(502, "notification provider test failed") from exc
    checked_at = datetime.now(UTC).isoformat()
    updated = await store.update(
        channel,
        {**channel.data, "health": "HEALTHY", "last_tested": checked_at, "last_error": None},
        actor_id=actor.actor_id,
        event_type="notification.channel_tested",
    )
    await store.update(
        credential,
        {
            **credential.data,
            "status": "ACTIVE",
            "last_tested": checked_at,
            "last_test_result": "HEALTHY",
        },
        actor_id=actor.actor_id,
        event_type="notification.credential_tested",
    )
    return {**_public_channel(updated, credential), "receipt": receipt}


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
    return (await store.update(item, {**item.data, "read": True}, actor_id=actor.actor_id)).public()
