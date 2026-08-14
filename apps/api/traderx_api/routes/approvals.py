from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.identity.authorization import Actor, Role
from traderx.strategies.approval import approval_payload, record_approval
from traderx.strategies.approval_model import ApprovalDecision, StrategyApproval
from traderx_api.dependencies import get_database_session
from traderx_api.middleware.context import correlation_id
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/approvals", tags=["Approvals"], dependencies=[Depends(authenticated_operation_context)]
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class ApprovalCommand(BaseModel):
    decision: str = Field(pattern="^(APPROVE_LIVE|REJECT|RETURN_TO_RESEARCH)$")
    reason: str = Field(min_length=8, max_length=2000)
    paper_run_id: UUID
    confirmation: Literal["CONFIRMED"]


@router.post("/strategies/{strategy_version_id}")
def decide_strategy(
    strategy_version_id: UUID,
    payload: ApprovalCommand,
    context: Operator,
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    approval = record_approval(
        database,
        Actor(Role(context.user.role), context.session.assurance, context.user.id),
        strategy_version_id=strategy_version_id,
        paper_run_id=payload.paper_run_id,
        decision=ApprovalDecision(payload.decision),
        reason=payload.reason,
        expected_etag=if_match,
        mfa_at=context.user.last_authenticated_at,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
    )
    database.commit()
    return approval_payload(approval)


@router.get("/strategies/{strategy_version_id}")
def approval_history(strategy_version_id: UUID, database: DatabaseSession) -> dict[str, object]:
    approvals = database.scalars(
        select(StrategyApproval)
        .where(StrategyApproval.strategy_version_id == strategy_version_id)
        .order_by(StrategyApproval.decided_at.desc())
    ).all()
    return {"items": [approval_payload(approval) for approval in approvals]}
