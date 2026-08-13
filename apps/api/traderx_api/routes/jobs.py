from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/jobs", tags=["Jobs"], dependencies=[Depends(authenticated_operation_context)]
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]


@router.get("")
def jobs(_: Viewer) -> dict[str, object]:
    return {"items": []}


@router.post("/{job_id}/cancel", status_code=202)
def cancel_job(job_id: str, _: Operator) -> dict[str, object]:
    return {"job_id": job_id, "status": "CANCEL_REQUESTED_AT_SAFE_BOUNDARY"}
