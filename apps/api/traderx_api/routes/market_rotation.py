from __future__ import annotations

from fastapi import APIRouter, Header

router = APIRouter(prefix="/market-rotation", tags=["Market Rotation"])


@router.get("/recommendations")
def replacement_recommendations() -> dict[str, object]:
    return {"items": [], "requires_human_replacement_review": True}


@router.get("/instruments/{instrument_id}/reactivation")
def reactivation_plan(instrument_id: str) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "state": "REVALIDATION_REQUIRED",
        "ends_in_human_approval": True,
    }


@router.post("/instruments/{instrument_id}/reactivation")
def request_reactivation(
    instrument_id: str, idempotency_key: str = Header(alias="Idempotency-Key")
) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "state": "REVALIDATION_REQUIRED",
        "idempotency_key": idempotency_key,
    }
