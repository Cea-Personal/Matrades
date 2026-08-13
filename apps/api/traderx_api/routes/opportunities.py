from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from traderx_api.routes.access import authenticated_operation_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/opportunities",
    tags=["Opportunities"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]


@router.get("")
def opportunities(_: Viewer) -> dict[str, object]:
    return {"items": [], "risk_authorization_is_separate": True, "no_execution_capability": True}


@router.get("/{opportunity_id}/recommendation")
def recommendation(opportunity_id: str, _: Viewer) -> dict[str, object]:
    return {
        "opportunity_id": opportunity_id,
        "state": "NO_RECOMMENDATION",
        "reason_codes": ["NO_CURRENT_RISK_DECISION"],
    }
