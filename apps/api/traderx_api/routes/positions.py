from __future__ import annotations

from fastapi import APIRouter, Header

router = APIRouter(prefix="/positions", tags=["Trade Monitoring"])


@router.get("")
def positions() -> dict[str, object]:
    return {"items": [], "broker_mode": "READ_ONLY"}


@router.put("/{position_id}/classification")
def correct_classification(
    position_id: str,
    payload: dict[str, object],
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
def position_thesis(position_id: str) -> dict[str, object]:
    return {"position_id": position_id, "immutable": True, "observations": []}
