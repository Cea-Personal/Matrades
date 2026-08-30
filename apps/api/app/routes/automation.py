from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles, require_step_up
from modules.identity.authorization import Actor, Role
from modules.trading.coordinator import current_broker_snapshot
from modules.trading.kill_switches import update_kill_switch
from modules.trading.models import ExecutionPermissionProfile, KillSwitchState
from modules.trading.permissions import update_permissions
from packages.shared.store import ResourceRecord, ResourceStore

router = APIRouter(prefix="/automation", tags=["Automation"])


@router.get("/trade-plans")
async def list_trade_plans(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [item.public() for item in await ResourceStore(db).list("trade_plan", actor.owner_id)]


@router.get("/trade-plans/{plan_id}")
async def get_trade_plan(
    plan_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await ResourceStore(db).get("trade_plan", plan_id, actor.owner_id)
    if item is None:
        raise HTTPException(status_code=404, detail="trade plan not found")
    return item.public()


@router.get("/execution-commands")
async def list_execution_commands(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [
        item.public() for item in await ResourceStore(db).list("execution_command", actor.owner_id)
    ]


@router.get("/execution-commands/{command_id}")
async def get_execution_command(
    command_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await ResourceStore(db).get("execution_command", command_id, actor.owner_id)
    if item is None:
        raise HTTPException(status_code=404, detail="execution command not found")
    return item.public()


@router.get("/operations")
async def operations(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    plans = await store.list("trade_plan", actor.owner_id)
    commands = await store.list("execution_command", actor.owner_id)
    trades = await store.list("active_trade", actor.owner_id)
    permissions = await store.list("execution_permission_profile", actor.owner_id)
    platform_kills = await store.list("platform_kill_switch", actor.owner_id)
    account_kills = await store.list("account_kill_switch", actor.owner_id)
    reconciliations = await store.list("reconciliation", actor.owner_id)
    grouped: dict[str, dict[str, list[dict]]] = {}
    for collection in (plans, commands, trades):
        for item in collection:
            account_id = str(item.data.get("account_id") or "unassigned")
            grouped.setdefault(
                account_id,
                {"trade_plans": [], "execution_commands": [], "active_trades": []},
            )
            target = (
                "trade_plans"
                if item.kind == "trade_plan"
                else "execution_commands"
                if item.kind == "execution_command"
                else "active_trades"
            )
            grouped[account_id][target].append(item.public())
    return {
        "trade_plans": [item.public() for item in plans],
        "execution_commands": [item.public() for item in commands],
        "active_trades": [item.public() for item in trades],
        "permission_profiles": [item.public() for item in permissions],
        "platform_kill_switch": platform_kills[0].public() if platform_kills else None,
        "account_kill_switches": [item.public() for item in account_kills],
        "reconciliations": [item.public() for item in reconciliations],
        "human_approval_required": False,
        "execution_mode": "AUTONOMOUS",
        "accounts": grouped,
    }


@router.get("/permissions/{account_id}")
async def permission_profile(
    account_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("execution_permission_profile", actor.owner_id)
    for item in records:
        if item.data.get("account_id") == str(account_id):
            return item.public()
    return {
        "account_id": str(account_id),
        "version": 1,
        "new_entry": False,
        "order_cancellation": False,
        "stop_loss_create_or_modify": False,
        "take_profit_create_or_modify": False,
        "partial_close": False,
        "full_exit": False,
        "reason": "no explicit execution permission profile configured",
        "effective": False,
    }


@router.put("/permissions/{account_id}")
async def set_permission_profile(
    account_id: UUID,
    payload: ExecutionPermissionProfile,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER))],
    _: Annotated[Actor, Depends(require_step_up("execution.permission"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if payload.account_id != account_id:
        raise HTTPException(status_code=422, detail="account_id does not match permission profile")
    store = ResourceStore(db)
    existing = await db.scalar(
        select(ResourceRecord)
        .where(
            ResourceRecord.kind == "execution_permission_profile",
            ResourceRecord.owner_id == actor.owner_id,
            ResourceRecord.state != "DELETED",
        )
        .with_for_update()
    )
    if existing is not None and existing.data.get("account_id") != str(account_id):
        existing = next(
            (
                item
                for item in await store.list("execution_permission_profile", actor.owner_id)
                if item.data.get("account_id") == str(account_id)
            ),
            None,
        )
    previous = ExecutionPermissionProfile.model_validate(existing.data) if existing else None
    try:
        effective = update_permissions(payload, previous=previous, step_up_verified=True)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    data = effective.model_dump(mode="json")
    if existing is None:
        item = await store.create(
            "execution_permission_profile",
            actor.owner_id,
            data,
            actor_id=actor.actor_id,
            event_type="execution_permission.changed",
        )
    else:
        item = await store.update(
            existing, data, actor_id=actor.actor_id, event_type="execution_permission.changed"
        )
    return item.public()


@router.get("/kill-switch/platform")
async def platform_kill_switch(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("platform_kill_switch", actor.owner_id)
    if records:
        return records[0].public()
    return KillSwitchState(scope="PLATFORM").model_dump(mode="json")


@router.get("/kill-switch/accounts/{account_id}")
async def account_kill_switch(
    account_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("account_kill_switch", actor.owner_id)
    for item in records:
        if item.data.get("account_id") == str(account_id):
            return item.public()
    return KillSwitchState(scope="ACCOUNT", account_id=account_id).model_dump(mode="json")


@router.put("/kill-switch/platform")
async def set_platform_kill_switch(
    payload: dict[str, Any],
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER))],
    _: Annotated[Actor, Depends(require_step_up("execution.kill_switch"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Persist a platform stop request; workers must re-read it before dispatch."""
    active = bool(payload.get("active", True))
    reason = str(payload.get("reason", "operator requested platform stop"))
    store = ResourceStore(db)
    existing = await db.scalar(
        select(ResourceRecord)
        .where(
            ResourceRecord.kind == "platform_kill_switch",
            ResourceRecord.owner_id == actor.owner_id,
            ResourceRecord.state != "DELETED",
        )
        .with_for_update()
    )
    previous = KillSwitchState.model_validate(existing.data) if existing else None
    health_verified = True
    if previous is not None and previous.active and not active:
        accounts = await store.list("account", actor.owner_id)
        for account in accounts:
            await current_broker_snapshot(db, actor.owner_id, account.id)
    data = update_kill_switch(
        KillSwitchState(scope="PLATFORM", active=active, reason=reason),
        previous=previous,
        step_up_verified=True,
        health_verified=health_verified,
    ).model_dump(mode="json")
    if existing is None:
        item = await store.create(
            "platform_kill_switch",
            actor.owner_id,
            data,
            actor_id=actor.actor_id,
            event_type="platform_kill_switch.changed",
        )
    else:
        item = await store.update(
            existing, data, actor_id=actor.actor_id, event_type="platform_kill_switch.changed"
        )
    return item.public()


@router.put("/kill-switch/accounts/{account_id}")
async def set_account_kill_switch(
    account_id: UUID,
    payload: dict[str, Any],
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER))],
    _: Annotated[Actor, Depends(require_step_up("execution.kill_switch"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    active = bool(payload.get("active", True))
    reason = str(payload.get("reason", "operator requested account stop"))
    store = ResourceStore(db)
    candidates = list(
        (
            await db.scalars(
                select(ResourceRecord)
                .where(
                    ResourceRecord.kind == "account_kill_switch",
                    ResourceRecord.owner_id == actor.owner_id,
                    ResourceRecord.state != "DELETED",
                )
                .with_for_update()
            )
        ).all()
    )
    existing = next(
        (item for item in candidates if item.data.get("account_id") == str(account_id)), None
    )
    previous = KillSwitchState.model_validate(existing.data) if existing else None
    health_verified = True
    if previous is not None and previous.active and not active:
        await current_broker_snapshot(db, actor.owner_id, account_id)
    data = update_kill_switch(
        KillSwitchState(
            scope="ACCOUNT", account_id=account_id, active=active, reason=reason
        ),
        previous=previous,
        step_up_verified=True,
        health_verified=health_verified,
    ).model_dump(mode="json")
    if existing is None:
        item = await store.create(
            "account_kill_switch",
            actor.owner_id,
            data,
            actor_id=actor.actor_id,
            event_type="account_kill_switch.changed",
        )
    else:
        item = await store.update(
            existing, data, actor_id=actor.actor_id, event_type="account_kill_switch.changed"
        )
    return item.public()
