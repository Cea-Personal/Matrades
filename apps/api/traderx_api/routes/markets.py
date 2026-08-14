from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from traderx.identity.authorization import Actor, Role
from traderx.jobs.model import BackgroundJob, JobState
from traderx.market_research.service import (
    active_markets_payload,
    deactivate_active_market,
    execute_market_research,
    instrument_library_payload,
    market_research_report,
    normalize_category,
)
from traderx.market_research.service import (
    approve_active_market as approve_active_market_service,
)
from traderx.shared.types import utc_now
from traderx_api.dependencies import get_database_session
from traderx_api.middleware.context import correlation_id
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/markets", tags=["Markets"], dependencies=[Depends(authenticated_operation_context)]
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class ResearchCommand(BaseModel):
    category: str = Field(pattern="^(COMMODITY|FOREX|CRYPTO|CRYPTOCURRENCY)$")
    methodology_version: str = Field(default="market-suitability-v1", min_length=1)
    weights: dict[str, Decimal] | None = None


class ActiveMarketCommand(BaseModel):
    candidate_assessment_id: UUID
    replace: bool = False
    confirmation: str = Field(pattern="^CONFIRMED$")
    reason: str = Field(min_length=8, max_length=2000)


class DeactivateMarketCommand(BaseModel):
    confirmation: str = Field(pattern="^DEACTIVATE$")
    reason: str = Field(min_length=8, max_length=2000)


def _actor(context: AuthenticationContext) -> Actor:
    return Actor(
        role=Role(context.user.role), assurance=context.session.assurance, id=context.user.id
    )


@router.get("/instruments")
def instrument_library(
    database: DatabaseSession,
    category: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    items = instrument_library_payload(database, category=category, status=status)
    return {
        "items": items,
        "category": normalize_category(category).value if category else None,
        "data_status": "AVAILABLE" if items else "NO_DATA",
    }


@router.post("/research", status_code=202)
def start_research(
    payload: ResearchCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    now = utc_now()
    job = BackgroundJob(
        job_type="MARKET_RESEARCH",
        owner_id=context.user.id,
        context={"category": normalize_category(payload.category).value},
        input_manifest={
            "methodology_version": payload.methodology_version,
            "weights": {key: str(value) for key, value in (payload.weights or {}).items()},
        },
        state=JobState.RUNNING,
        progress={"stage": "ELIGIBILITY_GATES"},
        started_at=now,
    )
    database.add(job)
    database.flush()
    run = execute_market_research(
        database,
        category=payload.category,
        method_version=payload.methodology_version,
        weights=payload.weights,
    )
    job.state = JobState.COMPLETED
    job.progress = {"stage": "COMPLETED", "run_id": str(run.id)}
    job.result_ref = f"/api/v1/markets/research/{run.id}"
    job.finished_at = utc_now()
    database.commit()
    response.headers["Location"] = job.result_ref
    return {
        "id": str(job.id),
        "run_id": str(run.id),
        "job_type": job.job_type,
        "category": run.category,
        "methodology_version": run.method_version,
        "state": run.state,
        "idempotency_key": idempotency_key,
    }


@router.get("/research/{run_id}")
def research_report(
    run_id: UUID, response: Response, database: DatabaseSession
) -> dict[str, object]:
    report = market_research_report(database, run_id)
    response.headers["ETag"] = f'"market-research-{run_id}"'
    return report


@router.get("/active")
def list_active_markets(database: DatabaseSession) -> dict[str, object]:
    return {"items": active_markets_payload(database), "maximum": 3}


@router.put("/active/{category}")
def approve_active_market(
    category: str,
    payload: ActiveMarketCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    assignment = approve_active_market_service(
        database,
        _actor(context),
        category=category,
        candidate_assessment_id=payload.candidate_assessment_id,
        expected_etag=if_match,
        replace=payload.replace,
        reason=payload.reason,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
    )
    database.commit()
    result = next(
        item for item in active_markets_payload(database) if item["id"] == str(assignment.id)
    )
    response.headers["ETag"] = str(result["etag"])
    return result


@router.delete("/active/{category}")
def deactivate_market(
    category: str,
    payload: DeactivateMarketCommand,
    context: Operator,
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    assignment = deactivate_active_market(
        database,
        _actor(context),
        category=category,
        expected_etag=if_match,
        reason=payload.reason,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
    )
    database.commit()
    return {
        "id": str(assignment.id),
        "category": assignment.category,
        "state": assignment.state,
        "deactivated": True,
    }
