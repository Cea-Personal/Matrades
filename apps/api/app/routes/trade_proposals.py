from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from modules.identity.authorization import Actor, Role
from modules.risk.authority import authoritative_risk_context
from modules.risk.engine import RiskEngine
from modules.risk.models import CandidateTrade, RiskContext, RiskDecision
from modules.trading.models import Hil2Action, ProposalState, TradeProposal
from packages.shared.domain_types import utc_now
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/trade-proposals", tags=["Trade proposals"])


class ProposalCreate(BaseModel):
    account_id: UUID
    context: RiskContext | None = None  # Deprecated input; server authority always replaces it.
    candidate: CandidateTrade
    targets: list[Decimal]
    invalidation: str
    strategy_id: UUID | None = None
    strategy_version: str
    regime: str
    evidence: list[str] = []
    critic_result: str = "Deterministic policy, risk and evidence checks passed"


class DecisionInput(BaseModel):
    action: Hil2Action
    reason: str | None = None


@router.get("")
async def list_proposals(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [x.public() for x in await ResourceStore(db).list("trade_proposal", actor.owner_id)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_proposal(
    payload: ProposalCreate,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raise HTTPException(
        status.HTTP_410_GONE,
        "legacy trade proposals are read-only evidence; create a validated Trade Plan instead",
    )
    context = await authoritative_risk_context(
        db, actor.owner_id, payload.account_id, payload.candidate
    )
    result = RiskEngine().evaluate(context, payload.candidate)
    proposal_id = uuid4()
    state = (
        ProposalState.BLOCKED
        if result.decision == RiskDecision.HARD_BLOCK
        else ProposalState.AWAITING_HIL2
    )
    reservation_id = None
    store = ResourceStore(db)
    if state == ProposalState.AWAITING_HIL2:
        reservation_id = uuid4()
        await store.create(
            "risk_reservation",
            actor.owner_id,
            {
                "account_id": str(payload.account_id),
                "proposal_id": str(proposal_id),
                "amount": str(result.snapshot.candidate_trade_risk),
                "expires_at": (utc_now() + timedelta(minutes=10)).isoformat(),
            },
            state="ACTIVE",
            record_id=reservation_id,
            actor_id=actor.actor_id,
            event_type="risk_reservation.created",
        )
    proposal = TradeProposal(
        id=proposal_id,
        owner_id=actor.owner_id,
        account_id=payload.account_id,
        instrument=payload.candidate.instrument,
        direction=payload.candidate.direction,
        entry=payload.candidate.entry_price,
        stop_loss=payload.candidate.stop_loss,
        targets=payload.targets,
        invalidation=payload.invalidation,
        approved_size=result.approved_size,
        risk=result,
        critic_result=payload.critic_result,
        strategy_id=payload.strategy_id,
        strategy_version=payload.strategy_version,
        regime=payload.regime,
        evidence=payload.evidence,
        state=state,
        reservation_id=reservation_id,
    )
    record = await store.create(
        "trade_proposal",
        actor.owner_id,
        proposal.model_dump(mode="json"),
        state=state.value,
        record_id=proposal.id,
        actor_id=actor.actor_id,
        event_type=(
            "trade_proposal.blocked"
            if state == ProposalState.BLOCKED
            else "trade_proposal.approval_requested"
        ),
    )
    return record.public()


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await ResourceStore(db).get("trade_proposal", proposal_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    return item.public()


@router.post("/{proposal_id}/decisions")
async def hil2_decision(
    proposal_id: UUID,
    payload: DecisionInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raise HTTPException(status.HTTP_410_GONE, "legacy proposal decisions are retired")
    store = ResourceStore(db)
    record = await store.get("trade_proposal", proposal_id, actor.owner_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    if record.state != ProposalState.AWAITING_HIL2:
        raise HTTPException(status.HTTP_409_CONFLICT, "proposal is not awaiting HIL-2")
    expires_at = record.data.get("expires_at")
    if expires_at and utc_now().isoformat() > expires_at:
        await store.update(record, state="EXPIRED", actor_id=actor.actor_id)
        raise HTTPException(status.HTTP_409_CONFLICT, "proposal expired")
    next_state = {
        Hil2Action.TAKE: ProposalState.AWAITING_MANUAL_ENTRY,
        Hil2Action.WAIT: ProposalState.WAITING,
        Hil2Action.REJECT: ProposalState.REJECTED,
    }[payload.action]
    reservation_id = record.data.get("reservation_id")
    if reservation_id:
        reservation = await store.get("risk_reservation", UUID(reservation_id), actor.owner_id)
        if reservation:
            reservation_state = "CONFIRMED" if payload.action == Hil2Action.TAKE else "RELEASED"
            await store.update(
                reservation,
                state=reservation_state,
                actor_id=actor.actor_id,
                event_type=f"risk_reservation.{reservation_state.lower()}",
            )
    data = {
        **record.data,
        "state": next_state.value,
        "decision": {
            "action": payload.action,
            "reason": payload.reason,
            "actor_id": str(actor.actor_id),
            "decided_at": utc_now().isoformat(),
        },
    }
    updated = await store.update(
        record,
        data,
        state=next_state.value,
        actor_id=actor.actor_id,
        event_type=f"trade_proposal.{payload.action.value.lower()}_recorded",
    )
    return updated.public()
