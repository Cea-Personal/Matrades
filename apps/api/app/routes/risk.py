from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db
from modules.accounts.snapshots import validate_snapshot
from modules.identity.authorization import Actor
from modules.risk.engine import RiskEngine
from modules.risk.models import CandidateTrade, RiskContext, RiskResult
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/risk", tags=["Risk"])


class RiskRequest(RiskContext):
    candidate: CandidateTrade


@router.post("/evaluate", response_model=RiskResult)
async def evaluate(
    request: RiskRequest,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RiskResult:
    validate_snapshot(request.account, request.account.account_id)
    result = RiskEngine().evaluate(request, request.candidate)
    await ResourceStore(db).audit(
        actor.owner_id,
        actor.actor_id,
        "risk.evaluated",
        "risk_evaluation",
        request.account.id,
        {
            "account_id": str(request.account.account_id),
            "decision": result.decision,
            "snapshot": result.snapshot.model_dump(mode="json"),
            "limiting_constraints": result.limiting_constraints,
        },
    )
    return result


@router.post("/snapshot", response_model=dict)
async def snapshot(
    context: RiskContext,
    _: Annotated[Actor, Depends(current_actor)],
) -> dict:
    validate_snapshot(context.account, context.account.account_id)
    return context.account.model_dump(mode="json")

