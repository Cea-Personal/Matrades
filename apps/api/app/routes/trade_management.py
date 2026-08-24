from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from modules.identity.authorization import Actor, Role
from modules.trading.active_trades import promote_actual
from modules.trading.broker_models import (
    ActiveTrade,
    ManagementRecommendation,
    RecommendationAction,
)
from modules.trading.hil3 import Hil3Action
from modules.trading.models import ProposalState, TradeProposal
from modules.trading.monitor import monitoring_facts
from modules.trading.monitor_agent import interpret
from modules.trading.reconciliation import reconcile
from packages.broker_sdk.schemas import BrokerSnapshot
from packages.shared.domain_types import utc_now
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/trade-management", tags=["Trade management"])


class MonitoringInput(BaseModel):
    trade_id: UUID
    current_price: Decimal
    bridge_fresh: bool = True


class RecommendationInput(BaseModel):
    action: RecommendationAction
    reason: str
    proposed_value: Decimal | None = None


class DecisionInput(BaseModel):
    action: Hil3Action
    reason: str | None = None


@router.post("/broker-snapshots", status_code=status.HTTP_202_ACCEPTED)
async def ingest_broker_snapshot(
    snapshot: BrokerSnapshot,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    existing_snapshots = [
        item
        for item in await store.list("broker_snapshot", actor.owner_id)
        if item.data.get("account_id") == str(snapshot.account_id)
    ]
    duplicate = next(
        (
            item
            for item in existing_snapshots
            if item.data.get("message_id") == str(snapshot.message_id)
        ),
        None,
    )
    if duplicate is not None:
        return {"sequence": snapshot.sequence, "reconciliations": [], "duplicate": True}
    if existing_snapshots and snapshot.sequence <= int(
        existing_snapshots[0].data.get("sequence", -1)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "out-of-order or replayed broker snapshot"
        )
    await store.create(
        "broker_snapshot",
        actor.owner_id,
        snapshot.model_dump(mode="json"),
        actor_id=actor.actor_id,
        event_type="broker.account_changed",
    )
    reconciliations: list[dict] = []
    for proposal_record in await store.list("trade_proposal", actor.owner_id):
        if proposal_record.state != ProposalState.AWAITING_MANUAL_ENTRY:
            continue
        proposal = TradeProposal.model_validate(proposal_record.data)
        if proposal.account_id != snapshot.account_id:
            continue
        result = reconcile(proposal, snapshot.positions)
        reconciliation_record = await store.create(
            "reconciliation",
            actor.owner_id,
            result.model_dump(mode="json"),
            state=result.state,
            actor_id=actor.actor_id,
            event_type=(
                "reconciliation.confirmed"
                if result.state == "MATCHED"
                else "reconciliation.confirmation_requested"
            ),
        )
        reconciliations.append(reconciliation_record.public())
        if result.selected_position_id:
            position = next(
                item
                for item in snapshot.positions
                if item.position_id == result.selected_position_id
            )
            active = promote_actual(actor.owner_id, proposal.id, position)
            await store.create(
                "active_trade",
                actor.owner_id,
                active.model_dump(mode="json"),
                state=active.state,
                record_id=active.id,
                actor_id=actor.actor_id,
                event_type="trade.position_activated",
            )
            await store.update(
                proposal_record,
                {
                    **proposal_record.data,
                    "state": "ACTIVE",
                    "actual_position": position.model_dump(mode="json"),
                },
                state="ACTIVE",
                actor_id=actor.actor_id,
                event_type="trade.position_activated",
            )
    return {"sequence": snapshot.sequence, "reconciliations": reconciliations}


@router.get("/reconciliations")
async def list_reconciliations(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("reconciliation", actor.owner_id)
    return [item.public() for item in records]


@router.get("/trades")
async def list_trades(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("active_trade", actor.owner_id)
    return [item.public() for item in records]


@router.post("/monitor")
async def monitor_trade(
    payload: MonitoringInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    trade_record = await store.get("active_trade", payload.trade_id, actor.owner_id)
    if trade_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "active trade not found")
    trade = ActiveTrade.model_validate(trade_record.data)
    policy_valid = bool(await store.list("guardrail", actor.owner_id))
    facts = monitoring_facts(trade, payload.current_price, policy_valid, payload.bridge_fresh)
    recommendation = interpret(trade.id, facts)
    item = await store.create(
        "management_recommendation",
        actor.owner_id,
        {**recommendation.model_dump(mode="json"), "policy_valid": policy_valid, "facts": facts},
        state="ACTION_REQUIRED" if recommendation.requires_hil3 else "HOLD",
        record_id=recommendation.id,
        actor_id=actor.actor_id,
        event_type="trade.monitoring_updated",
    )
    return item.public()


@router.post("/trades/{trade_id}/recommendations", status_code=status.HTTP_201_CREATED)
async def create_recommendation(
    trade_id: UUID,
    payload: RecommendationInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    trade = await store.get("active_trade", trade_id, actor.owner_id)
    if trade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "active trade not found")
    policy_valid = bool(await store.list("guardrail", actor.owner_id))
    recommendation = ManagementRecommendation(
        trade_id=trade_id,
        action=payload.action,
        reason=payload.reason,
        proposed_value=payload.proposed_value,
        requires_hil3=payload.action != RecommendationAction.HOLD,
    )
    item = await store.create(
        "management_recommendation",
        actor.owner_id,
        {**recommendation.model_dump(mode="json"), "policy_valid": policy_valid},
        state="ACTION_REQUIRED" if recommendation.requires_hil3 else "HOLD",
        record_id=recommendation.id,
        actor_id=actor.actor_id,
        event_type=(
            "trade_management.approval_requested"
            if recommendation.requires_hil3
            else "trade.monitoring_updated"
        ),
    )
    return item.public()


@router.get("/recommendations")
async def list_recommendations(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("management_recommendation", actor.owner_id)
    return [item.public() for item in records]


@router.post("/recommendations/{recommendation_id}/decisions")
async def hil3_decision(
    recommendation_id: UUID,
    payload: DecisionInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("management_recommendation", recommendation_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recommendation not found")
    if item.state != "ACTION_REQUIRED":
        raise HTTPException(status.HTTP_409_CONFLICT, "recommendation is not awaiting HIL-3")
    policy_valid = bool(await store.list("guardrail", actor.owner_id))
    if payload.action == Hil3Action.APPROVE and not policy_valid:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "recommendation no longer complies with policy"
        )
    next_state = {
        Hil3Action.APPROVE: "APPROVED_MANUAL_ACTION",
        Hil3Action.WAIT: "WAITING",
        Hil3Action.REJECT: "REJECTED",
    }[payload.action]
    updated = await store.update(
        item,
        {
            **item.data,
            "decision": payload.action,
            "decision_reason": payload.reason,
            "decided_at": utc_now().isoformat(),
            "broker_mutated": False,
            "manual_execution_required": payload.action == Hil3Action.APPROVE,
        },
        state=next_state,
        actor_id=actor.actor_id,
        event_type=f"trade_management.{payload.action.value.lower()}",
    )
    return updated.public()
