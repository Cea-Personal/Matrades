from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/market-rotation",
    tags=["Market Rotation"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]


@router.get("/recommendations")
def replacement_recommendations(_: Viewer) -> dict[str, object]:
    return {"items": [], "requires_human_replacement_review": True}


@router.get("/instruments/{instrument_id}/reactivation")
def reactivation_plan(instrument_id: str, _: Viewer) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "state": "REVALIDATION_REQUIRED",
        "ends_in_human_approval": True,
    }


@router.post("/instruments/{instrument_id}/reactivation")
def request_reactivation(
    instrument_id: str,
    _: Operator,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "state": "REVALIDATION_REQUIRED",
        "idempotency_key": idempotency_key,
    }
