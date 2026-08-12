from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/operations", tags=["Operations"])


@router.get("/health")
def health() -> dict[str, object]:
    return {"status": "UNKNOWN", "secrets_redacted": True}


@router.get("/audit")
def audit() -> dict[str, object]:
    return {"items": [], "append_only": True, "redacted": True}
