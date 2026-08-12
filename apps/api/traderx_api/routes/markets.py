from __future__ import annotations

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/markets", tags=["Markets"])


class ResearchCommand(BaseModel):
    category: str = Field(pattern="^(COMMODITY|FOREX|CRYPTOCURRENCY)$")
    methodology_version: str = Field(min_length=1)


@router.get("/instruments")
def instrument_library(category: str | None = None) -> dict[str, object]:
    return {"items": [], "category": category, "data_status": "NO_DATA"}


@router.post("/research", status_code=202)
def start_research(
    payload: ResearchCommand, idempotency_key: str = Header(alias="Idempotency-Key")
) -> dict[str, object]:
    return {
        "job_type": "market_research",
        "category": payload.category,
        "methodology_version": payload.methodology_version,
        "idempotency_key": idempotency_key,
    }


@router.get("/research/{run_id}")
def research_report(run_id: str, response: Response) -> dict[str, object]:
    response.headers["ETag"] = '"market-research-0"'
    return {"id": run_id, "state": "QUEUED", "candidates": [], "ranking_is_not_activation": True}


@router.put("/active/{category}")
def approve_active_market(
    category: str,
    payload: dict[str, object],
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "category": category,
        "accepted": True,
        "requires_explicit_replacement_review": True,
        "version": if_match,
        "idempotency_key": idempotency_key,
        "payload": payload,
    }
