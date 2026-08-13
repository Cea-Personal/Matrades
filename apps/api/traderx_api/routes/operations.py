from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from traderx_api.routes.access import authenticated_operation_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/operations",
    tags=["Operations"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]


@router.get("/health")
def health(_: Viewer) -> dict[str, object]:
    return {"status": "UNKNOWN", "secrets_redacted": True}


@router.get("/audit")
def audit(_: Viewer) -> dict[str, object]:
    return {"items": [], "append_only": True, "redacted": True}
