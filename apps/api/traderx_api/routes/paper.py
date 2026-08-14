from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.jobs.model import BackgroundJob, JobState
from traderx.paper.model import PaperRun
from traderx.paper.service import execute_paper_run, paper_run_payload
from traderx.shared.types import InvalidTransition, utc_now
from traderx_api.dependencies import get_database_session
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/paper", tags=["Paper Trading"], dependencies=[Depends(authenticated_operation_context)]
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class PaperRunCommand(BaseModel):
    strategy_version_id: UUID
    validation_run_id: UUID
    evidence_manifest_hash: str | None = None


@router.post("/runs", status_code=202)
def start_paper_run(
    payload: PaperRunCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    run = execute_paper_run(
        database,
        strategy_version_id=payload.strategy_version_id,
        validation_run_id=payload.validation_run_id,
        evidence_manifest_hash=payload.evidence_manifest_hash,
    )
    now = utc_now()
    result_ref = f"/api/v1/paper/runs/{run.id}"
    job = BackgroundJob(
        job_type="PAPER_EVALUATION",
        owner_id=context.user.id,
        context={"paper_run_id": str(run.id)},
        input_manifest={"evidence_hash": run.evidence_hash},
        state=JobState.COMPLETED,
        progress={"stage": "COMPLETED", "completed": 1, "total": 1},
        started_at=now,
        finished_at=now,
        result_ref=result_ref,
    )
    database.add(job)
    database.commit()
    response.headers["Location"] = result_ref
    response.headers["Idempotency-Key"] = idempotency_key
    return {"job": {"id": str(job.id), "state": job.state}, "run": paper_run_payload(database, run)}


@router.get("/runs")
def list_paper_runs(database: DatabaseSession) -> dict[str, object]:
    runs = database.scalars(select(PaperRun).order_by(PaperRun.started_at.desc())).all()
    return {"items": [paper_run_payload(database, run) for run in runs]}


@router.get("/runs/{paper_run_id}")
def paper_run(
    paper_run_id: UUID, database: DatabaseSession, response: Response
) -> dict[str, object]:
    run = database.get(PaperRun, paper_run_id)
    if run is None:
        raise InvalidTransition("the requested paper run does not exist")
    response.headers["ETag"] = f'"paper-run-{run.id}-{run.version}"'
    return paper_run_payload(database, run)
