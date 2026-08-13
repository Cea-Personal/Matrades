from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from traderx_api.routes.access import authenticated_operation_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]


@router.get("/inbox")
def inbox(_: Viewer) -> dict[str, object]:
    return {"items": []}


@router.get("/preferences")
def preferences(_: Viewer) -> dict[str, object]:
    return {"items": []}
