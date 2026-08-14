from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.types import InvalidTransition, utc_now
from traderx.validation.model import BacktestRun, ValidationRun
from traderx.validation.service import (
    backtest_payload,
    execute_backtest,
    execute_validation,
    validation_payload,
)
from traderx_api.dependencies import get_database_session
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/validation",
    tags=["Validation"],
    dependencies=[Depends(authenticated_operation_context)],
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class BacktestCommand(BaseModel):
    strategy_version_id: UUID
    manifest_hash: str | None = Field(default=None, min_length=8, max_length=128)


class ValidationCommand(BacktestCommand):
    backtest_run_id: UUID
    seed: int = 20260813


def _completed_job(
    database: Session,
    context: AuthenticationContext,
    *,
    job_type: str,
    target_id: UUID,
    result_ref: str,
) -> BackgroundJob:
    now = utc_now()
    job = BackgroundJob(
        job_type=job_type,
        owner_id=context.user.id,
        context={"target_id": str(target_id)},
        input_manifest={"target_id": str(target_id)},
        state=JobState.COMPLETED,
        progress={"stage": "COMPLETED", "completed": 1, "total": 1},
        started_at=now,
        finished_at=now,
        result_ref=result_ref,
    )
    database.add(job)
    database.flush()
    return job


@router.post("/backtests", status_code=202)
def start_backtest(
    payload: BacktestCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    run = execute_backtest(
        database,
        strategy_version_id=payload.strategy_version_id,
        requested_manifest_hash=payload.manifest_hash,
    )
    result_ref = f"/api/v1/validation/backtests/{run.id}"
    job = _completed_job(
        database, context, job_type="BACKTEST", target_id=run.id, result_ref=result_ref
    )
    database.commit()
    response.headers["Location"] = result_ref
    response.headers["Idempotency-Key"] = idempotency_key
    return {"job": {"id": str(job.id), "state": job.state}, "run": backtest_payload(run)}


@router.get("/backtests/{run_id}")
def get_backtest(run_id: UUID, database: DatabaseSession) -> dict[str, object]:
    run = database.get(BacktestRun, run_id)
    if run is None:
        raise InvalidTransition("the requested backtest does not exist")
    return backtest_payload(run)


@router.get("/backtests")
def list_backtests(database: DatabaseSession) -> dict[str, object]:
    runs = database.scalars(select(BacktestRun).order_by(BacktestRun.created_at.desc())).all()
    return {"items": [backtest_payload(run) for run in runs]}


@router.post("/runs", status_code=202)
def start_validation(
    payload: ValidationCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    run = execute_validation(
        database,
        strategy_version_id=payload.strategy_version_id,
        backtest_run_id=payload.backtest_run_id,
        seed=payload.seed,
        requested_manifest_hash=payload.manifest_hash,
    )
    result_ref = f"/api/v1/validation/runs/{run.id}"
    job = _completed_job(
        database, context, job_type="VALIDATION", target_id=run.id, result_ref=result_ref
    )
    database.commit()
    response.headers["Location"] = result_ref
    response.headers["Idempotency-Key"] = idempotency_key
    return {"job": {"id": str(job.id), "state": job.state}, "run": validation_payload(run)}


@router.get("/runs/{run_id}")
def get_validation(run_id: UUID, database: DatabaseSession) -> dict[str, object]:
    run = database.get(ValidationRun, run_id)
    if run is None:
        raise InvalidTransition("the requested validation does not exist")
    return validation_payload(run)


@router.get("/runs")
def list_validations(database: DatabaseSession) -> dict[str, object]:
    runs = database.scalars(select(ValidationRun).order_by(ValidationRun.created_at.desc())).all()
    return {"items": [validation_payload(run) for run in runs]}
