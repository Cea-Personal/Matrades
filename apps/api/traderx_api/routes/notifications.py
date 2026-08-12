from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/inbox")
def inbox() -> dict[str, object]:
    return {"items": []}


@router.get("/preferences")
def preferences() -> dict[str, object]:
    return {"items": []}
