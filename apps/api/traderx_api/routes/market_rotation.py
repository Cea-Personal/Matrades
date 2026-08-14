from __future__ import annotations

from datetime import UTC, timedelta
from decimal import Decimal
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from traderx.instruments.reactivation_service import begin_reactivation
from traderx.jobs.model import BackgroundJob, JobState
from traderx.journal.model import JournalEntry
from traderx.market_data.model import Instrument, InstrumentAlias
from traderx.market_research.model import (
    ActiveMarketAssignment,
    AssignmentState,
    CandidateAssessment,
)
from traderx.market_research.replacement import compare_current_to_candidate
from traderx.research.model import ResearchExperiment
from traderx.shared.types import InvalidTransition, utc_now
from traderx.strategies.model import Strategy, StrategyVersion
from traderx.strategies.staleness import EvidenceFreshness, RevalidationPlan, classify_evidence
from traderx.validation.model import ValidationRun
from traderx_api.dependencies import get_database_session
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/market-rotation",
    tags=["Market Rotation"],
    dependencies=[Depends(authenticated_operation_context)],
)
Viewer = Annotated[AuthenticationContext, Depends(authenticated_operation_context)]
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


@router.get("/recommendations")
def replacement_recommendations(_: Viewer, database: DatabaseSession) -> dict[str, object]:
    items: list[dict[str, object]] = []
    active = database.scalars(
        select(ActiveMarketAssignment).where(
            ActiveMarketAssignment.state == AssignmentState.ACTIVE,
            ActiveMarketAssignment.effective_to.is_(None),
        )
    ).all()
    for assignment in active:
        current_assessment = database.get(CandidateAssessment, assignment.candidate_assessment_id)
        candidate = database.scalar(
            select(CandidateAssessment)
            .join(Instrument, Instrument.id == CandidateAssessment.instrument_id)
            .where(
                Instrument.category == assignment.category,
                CandidateAssessment.eligible.is_(True),
                CandidateAssessment.instrument_id != assignment.instrument_id,
                CandidateAssessment.score.is_not(None),
            )
            .order_by(CandidateAssessment.score.desc())
            .limit(1)
        )
        if current_assessment is None or candidate is None:
            continue
        comparison = compare_current_to_candidate(
            current_score=Decimal(str(current_assessment.score or 0)),
            candidate_score=Decimal(str(candidate.score or 0)),
            minimum_improvement=Decimal("0.05"),
        )
        current_instrument = database.get(Instrument, assignment.instrument_id)
        candidate_instrument = database.get(Instrument, candidate.instrument_id)
        items.append(
            {
                "category": assignment.category,
                "current": {
                    "instrument_id": str(assignment.instrument_id),
                    "symbol": current_instrument.symbol if current_instrument else "UNKNOWN",
                    "score": str(current_assessment.score),
                },
                "candidate": {
                    "instrument_id": str(candidate.instrument_id),
                    "candidate_assessment_id": str(candidate.id),
                    "symbol": candidate_instrument.symbol if candidate_instrument else "UNKNOWN",
                    "score": str(candidate.score),
                },
                "recommended": comparison.recommended,
                "improvement": str(comparison.improvement),
                "reason_codes": list(comparison.reason_codes),
                "replacement_is_never_automatic": True,
            }
        )
    return {"items": items, "requires_human_replacement_review": True}


@router.get("/history")
def assignment_history(_: Viewer, database: DatabaseSession) -> dict[str, object]:
    assignments = database.scalars(
        select(ActiveMarketAssignment).order_by(ActiveMarketAssignment.effective_from.desc())
    ).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "category": item.category,
                "instrument_id": str(item.instrument_id),
                "state": item.state,
                "effective_from": _iso(item.effective_from),
                "effective_to": _iso(item.effective_to) if item.effective_to else None,
                "approval_reason": item.approval_reason,
            }
            for item in assignments
        ]
    }


@router.get("/instruments/{instrument_id}/reactivation")
def reactivation_plan(
    instrument_id: UUID, _: Viewer, database: DatabaseSession
) -> dict[str, object]:
    instrument = database.get(Instrument, instrument_id)
    if instrument is None:
        raise InvalidTransition("the requested instrument does not exist")
    return _reactivation_payload(database, instrument)


@router.post("/instruments/{instrument_id}/reactivation", status_code=202)
def request_reactivation(
    instrument_id: UUID,
    context: Operator,
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    instrument = database.get(Instrument, instrument_id)
    if instrument is None:
        raise InvalidTransition("the requested instrument does not exist")
    plan = _reactivation_payload(database, instrument)
    steps = cast(list[str], plan["steps"])
    knowledge = cast(dict[str, int], plan["knowledge"])
    outcome = begin_reactivation(
        RevalidationPlan(
            EvidenceFreshness(str(plan["state"])),
            tuple(steps),
        ),
        preserved_knowledge=knowledge,
    )
    now = utc_now()
    job = BackgroundJob(
        job_type="INSTRUMENT_REACTIVATION_PLAN",
        owner_id=context.user.id,
        context={"instrument_id": str(instrument.id)},
        input_manifest={
            "plan": plan,
            "preserved_knowledge": outcome.preserved_knowledge,
            "automatically_activated": outcome.automatically_activated,
        },
        state=JobState.COMPLETED,
        progress={"stage": "PLAN_CREATED", "completed": 1, "total": 1},
        started_at=now,
        finished_at=now,
        result_ref=f"/api/v1/market-rotation/instruments/{instrument.id}/reactivation",
    )
    database.add(job)
    # Deliberately preserve INACTIVE/QUARANTINED. A later market approval is required.
    database.commit()
    return {
        **plan,
        "workflow_state": outcome.state,
        "job": {"id": str(job.id), "state": job.state},
        "idempotency_key": idempotency_key,
    }


def _reactivation_payload(database: Session, instrument: Instrument) -> dict[str, object]:
    strategies = database.scalars(
        select(Strategy).where(Strategy.instrument_id == instrument.id)
    ).all()
    strategy_ids = [strategy.id for strategy in strategies]
    version_ids = (
        list(
            database.scalars(
                select(StrategyVersion.id).where(StrategyVersion.strategy_id.in_(strategy_ids))
            )
        )
        if strategy_ids
        else []
    )
    latest_validation = (
        database.scalar(
            select(ValidationRun)
            .where(ValidationRun.strategy_version_id.in_(version_ids))
            .order_by(ValidationRun.created_at.desc())
            .limit(1)
        )
        if version_ids
        else None
    )
    now = utc_now()
    validated_at = latest_validation.created_at if latest_validation else now - timedelta(days=365)
    validated_at = validated_at if validated_at.tzinfo else validated_at.replace(tzinfo=UTC)
    closes = instrument.contract_spec.get("closes")
    data_gap = not isinstance(closes, list) or len(closes) < 30
    plan = classify_evidence(validated_at=validated_at, now=now, data_gap=data_gap)
    return {
        "instrument_id": str(instrument.id),
        "symbol": instrument.symbol,
        "current_status": instrument.status,
        "state": plan.freshness,
        "steps": list(plan.steps),
        "data_gaps": [{"kind": "HISTORICAL_COVERAGE", "required_observations": 30}]
        if data_gap
        else [],
        "knowledge": {
            "aliases": database.scalar(
                select(func.count())
                .select_from(InstrumentAlias)
                .where(InstrumentAlias.instrument_id == instrument.id)
            )
            or 0,
            "strategies": len(strategies),
            "strategy_versions": len(version_ids),
            "journal_entries": database.scalar(
                select(func.count())
                .select_from(JournalEntry)
                .where(JournalEntry.instrument_id == instrument.id)
            )
            or 0,
            "research_experiments": database.scalar(
                select(func.count()).select_from(ResearchExperiment)
            )
            or 0,
        },
        "ends_in_human_approval": True,
        "automatically_activated": False,
    }


def _iso(value: object) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)
