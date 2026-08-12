from __future__ import annotations

from fastapi import APIRouter, Header

router = APIRouter(prefix="/journal", tags=["Journal"])


@router.get("/entries")
def entries() -> dict[str, object]:
    return {"items": []}


@router.post("/entries/{entry_id}/annotations", status_code=201)
def annotate(
    entry_id: str,
    payload: dict[str, object],
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "entry_id": entry_id,
        "annotation": payload,
        "idempotency_key": idempotency_key,
        "append_only": True,
    }


@router.get("/analytics")
def analytics(dimension: str = "instrument") -> dict[str, object]:
    return {"dimension": dimension, "groups": {}}


@router.post("/proposals", status_code=201)
def proposal(
    payload: dict[str, object], idempotency_key: str = Header(alias="Idempotency-Key")
) -> dict[str, object]:
    return {"proposal": payload, "state": "PROPOSED", "idempotency_key": idempotency_key}
