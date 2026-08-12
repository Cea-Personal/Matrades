from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

router = APIRouter(prefix="/approvals", tags=["Approvals"])


class ApprovalCommand(BaseModel):
    decision: str = Field(pattern="^(APPROVE_LIVE|REJECT|RETURN_TO_RESEARCH)$")
    reason: str = Field(min_length=1)


@router.post("/strategies/{strategy_version_id}")
def decide_strategy(
    strategy_version_id: str,
    payload: ApprovalCommand,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "strategy_version_id": strategy_version_id,
        "decision": payload.decision,
        "requires_recent_mfa": True,
        "version": if_match,
        "idempotency_key": idempotency_key,
    }
