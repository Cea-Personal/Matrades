from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from traderx.jobs.model import BackgroundJob, JobState
from traderx.research.model import ResearchExperiment, ResearchJobDetail
from traderx.shared.types import InvalidTransition, utc_now


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    purpose: str
    inputs: dict[str, object]
    parameters: dict[str, object]


def manifest_for(request: ResearchRequest) -> str:
    body = json.dumps(
        {"purpose": request.purpose, "inputs": request.inputs, "parameters": request.parameters},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def summarize(outcomes: list[dict[str, object]]) -> dict[str, object]:
    accepted = sum(1 for item in outcomes if item.get("outcome") == "ACCEPTED")
    return {"total": len(outcomes), "accepted": accepted, "rejected": len(outcomes) - accepted}


def create_research_job(
    database: Session,
    *,
    owner_id: UUID,
    request: ResearchRequest,
) -> tuple[BackgroundJob, ResearchJobDetail]:
    """Persist the frozen input manifest before any experiment is evaluated."""

    now = utc_now()
    manifest_hash = manifest_for(request)
    job = BackgroundJob(
        job_type="STRATEGY_RESEARCH",
        owner_id=owner_id,
        context={"purpose": request.purpose},
        input_manifest={
            "hash": manifest_hash,
            "inputs": request.inputs,
            "parameters": request.parameters,
        },
        state=JobState.QUEUED,
        progress={"completed_units": 0, "total_units": 0, "message": "Queued"},
    )
    database.add(job)
    database.flush()
    detail = ResearchJobDetail(
        job_id=job.id,
        purpose=request.purpose,
        input_manifest=job.input_manifest,
        result_summary={},
        created_at=now,
    )
    database.add(detail)
    database.flush()
    return job, detail


def record_experiment(
    database: Session,
    *,
    research_detail_id: UUID,
    parameters: dict[str, object],
    outcome: str,
) -> ResearchExperiment:
    detail = database.get(ResearchJobDetail, research_detail_id)
    if detail is None:
        raise InvalidTransition("the research job does not exist")
    if outcome not in {"ACCEPTED", "REJECTED", "FAILED"}:
        raise InvalidTransition("the research outcome is invalid")
    document = {
        "input_manifest": detail.input_manifest,
        "parameters": parameters,
        "outcome": outcome,
    }
    experiment = ResearchExperiment(
        research_job_id=detail.id,
        manifest_hash=hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest(),
        parameters=parameters,
        outcome=outcome,
        created_at=utc_now(),
    )
    database.add(experiment)
    database.flush()
    return experiment


def complete_research_job(
    database: Session,
    *,
    job_id: UUID,
    detail_id: UUID,
    outcomes: list[dict[str, object]],
) -> dict[str, object]:
    job = database.get(BackgroundJob, job_id)
    detail = database.get(ResearchJobDetail, detail_id)
    if job is None or detail is None or detail.job_id != job.id:
        raise InvalidTransition("research job evidence does not match")
    if JobState(job.state or JobState.QUEUED) == JobState.QUEUED:
        job.transition(JobState.RUNNING)
    result = summarize(outcomes)
    detail.result_summary = result
    job.progress = {"completed_units": len(outcomes), "total_units": len(outcomes), "message": "Completed"}
    job.result_ref = f"research:{detail.id}"
    job.transition(JobState.COMPLETED)
    job.finished_at = utc_now()
    database.flush()
    return result
