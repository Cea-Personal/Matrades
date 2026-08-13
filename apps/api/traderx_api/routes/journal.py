from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/journal", tags=["Journal"], dependencies=[Depends(authenticated_operation_context)]
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]


@router.get("/entries")
def entries(_: Viewer) -> dict[str, object]:
    return {"items": []}


@router.post("/entries/{entry_id}/annotations", status_code=201)
def annotate(
    entry_id: str,
    payload: dict[str, object],
    _: Operator,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "entry_id": entry_id,
        "annotation": payload,
        "idempotency_key": idempotency_key,
        "append_only": True,
    }


@router.get("/analytics")
def analytics(_: Viewer, dimension: str = "instrument") -> dict[str, object]:
    return {"dimension": dimension, "groups": {}}


@router.post("/proposals", status_code=201)
def proposal(
    payload: dict[str, object],
    _: Operator,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {"proposal": payload, "state": "PROPOSED", "idempotency_key": idempotency_key}
