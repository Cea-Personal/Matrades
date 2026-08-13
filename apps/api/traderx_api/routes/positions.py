from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/positions", tags=["Trade Monitoring"], dependencies=[Depends(authenticated_operation_context)]
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]


@router.get("")
def positions(_: Viewer) -> dict[str, object]:
    return {"items": [], "broker_mode": "READ_ONLY"}


@router.put("/{position_id}/classification")
def correct_classification(
    position_id: str,
    payload: dict[str, object],
    _: Operator,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "position_id": position_id,
        "payload": payload,
        "version": if_match,
        "idempotency_key": idempotency_key,
        "audited": True,
    }


@router.get("/{position_id}/thesis")
def position_thesis(position_id: str, _: Viewer) -> dict[str, object]:
    return {"position_id": position_id, "immutable": True, "observations": []}
