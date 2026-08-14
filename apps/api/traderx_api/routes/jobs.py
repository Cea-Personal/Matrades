from __future__ import annotations

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.types import InvalidTransition, utc_now
from traderx_api.dependencies import get_database_session
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/jobs", tags=["Jobs"], dependencies=[Depends(authenticated_operation_context)]
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class JobAction(BaseModel):
    action: Literal["CANCEL", "PAUSE", "RESUME", "RETRY"]


@router.get("")
def jobs(_: Viewer, database: DatabaseSession) -> dict[str, object]:
    items = database.scalars(select(BackgroundJob).order_by(BackgroundJob.created_at.desc())).all()
    return {"items": [_payload(job) for job in items]}


@router.get("/{job_id}")
def job_detail(job_id: UUID, _: Viewer, database: DatabaseSession) -> dict[str, object]:
    job = database.get(BackgroundJob, job_id)
    if job is None:
        raise InvalidTransition("the requested background job does not exist")
    return _payload(job)


@router.get("/{job_id}/events", response_class=StreamingResponse)
def job_events(job_id: UUID, _: Viewer, database: DatabaseSession) -> StreamingResponse:
    """Return an authenticated progress event; EventSource reconnects until terminal state."""

    job = database.get(BackgroundJob, job_id)
    if job is None:
        raise InvalidTransition("the requested background job does not exist")
    body = f"retry: 5000\nevent: job\ndata: {json.dumps(_payload(job))}\n\n"
    return StreamingResponse(
        iter((body,)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/{job_id}/actions", status_code=202)
def control_job(
    job_id: UUID,
    payload: JobAction,
    _: Operator,
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    job = database.get(BackgroundJob, job_id)
    if job is None:
        raise InvalidTransition("the requested background job does not exist")
    now = utc_now()
    if payload.action == "CANCEL":
        if job.state == JobState.QUEUED:
            job.transition(JobState.CANCELLED)
            job.finished_at = now
        elif job.state == JobState.RUNNING:
            job.cancel_requested_at = now
        else:
            raise InvalidTransition("this job cannot be cancelled from its current state")
    elif payload.action == "PAUSE":
        if job.state != JobState.RUNNING:
            raise InvalidTransition("only a running job can pause at a safe checkpoint")
        job.pause_requested_at = now
    elif payload.action == "RESUME":
        job.transition(JobState.QUEUED)
        job.pause_requested_at = None
    else:
        if job.state != JobState.FAILED:
            raise InvalidTransition("only a failed job can be retried")
        job.transition(JobState.QUEUED)
        job.error_code = None
        job.finished_at = None
    database.commit()
    database.refresh(job)
    return {**_payload(job), "idempotency_key": idempotency_key}


@router.post("/{job_id}/cancel", status_code=202)
def cancel_job(job_id: UUID, _: Operator, database: DatabaseSession) -> dict[str, object]:
    job = database.get(BackgroundJob, job_id)
    if job is None:
        raise InvalidTransition("the requested background job does not exist")
    now = utc_now()
    if job.state == JobState.QUEUED:
        job.transition(JobState.CANCELLED)
        job.finished_at = now
    elif job.state == JobState.RUNNING:
        job.cancel_requested_at = now
    else:
        raise InvalidTransition("this job cannot be cancelled from its current state")
    database.commit()
    return {**_payload(job), "status": "CANCEL_REQUESTED_AT_SAFE_BOUNDARY"}


def _payload(job: BackgroundJob) -> dict[str, object]:
    actions: list[str] = []
    if job.state in {JobState.QUEUED, JobState.RUNNING}:
        actions.append("CANCEL")
    if job.state == JobState.RUNNING:
        actions.append("PAUSE")
    if job.state == JobState.PAUSED:
        actions.append("RESUME")
    if job.state == JobState.FAILED:
        actions.append("RETRY")
    return {
        "id": str(job.id),
        "type": job.job_type,
        "state": job.state,
        "progress": job.progress,
        "attempt_count": job.attempt_count,
        "result_ref": job.result_ref,
        "error_code": job.error_code,
        "cancel_requested": job.cancel_requested_at is not None,
        "pause_requested": job.pause_requested_at is not None,
        "available_actions": actions,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
