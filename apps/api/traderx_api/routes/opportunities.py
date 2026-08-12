from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


@router.get("")
def opportunities() -> dict[str, object]:
    return {"items": [], "risk_authorization_is_separate": True, "no_execution_capability": True}


@router.get("/{opportunity_id}/recommendation")
def recommendation(opportunity_id: str) -> dict[str, object]:
    return {
        "opportunity_id": opportunity_id,
        "state": "NO_RECOMMENDATION",
        "reason_codes": ["NO_CURRENT_RISK_DECISION"],
    }
