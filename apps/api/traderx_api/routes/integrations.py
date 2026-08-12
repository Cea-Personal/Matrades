from __future__ import annotations

from fastapi import APIRouter, Header

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("")
def integrations() -> dict[str, object]:
    return {"items": [], "credentials_are_write_only": True}


@router.post("/{integration_id}/rotate", status_code=202)
def rotate_credential(
    integration_id: str, idempotency_key: str = Header(alias="Idempotency-Key")
) -> dict[str, object]:
    return {
        "integration_id": integration_id,
        "status": "ROTATION_REQUESTED",
        "idempotency_key": idempotency_key,
    }
