from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.identity.authorization import Actor, Role
from traderx.integrations.model import Integration
from traderx.integrations.llm_profiles import model_prompt_profile
from traderx.jobs.model import BackgroundJob
from traderx.market_data.model import Instrument
from traderx.market_research.model import (
    ActiveMarketAssignment,
    AssignmentState,
    CandidateAssessment,
    MarketResearchModelConfiguration,
)
from traderx.research.model import ResearchJobDetail
from traderx.research.service import ResearchRequest, create_research_job
from traderx.strategies.ai_research import strategy_blueprint_for, validate_selection
from traderx.strategies.lifecycle import (
    create_immutable_version,
    create_strategy_with_version,
    definition_from_payload,
    strategy_payload,
    strategy_version_payload,
)
from traderx.strategies.model import Strategy, StrategyVersion
from traderx_api.dependencies import get_database_session
from traderx_api.middleware.context import correlation_id
from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/strategies",
    tags=["Strategies"],
    dependencies=[Depends(authenticated_operation_context)],
)
research_router = APIRouter(
    prefix="/research-jobs",
    tags=["Research and Strategies"],
    dependencies=[Depends(authenticated_operation_context)],
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class StrategyDefinitionCommand(BaseModel):
    regime: str = Field(min_length=1, max_length=64)
    direction: Literal["LONG", "SHORT", "BOTH"] = "BOTH"
    timeframes: list[str] = Field(min_length=1)
    conditions: list[dict[str, object]] = Field(min_length=1)
    filters: list[dict[str, object]] = Field(default_factory=list)
    stop: dict[str, object]
    target: dict[str, object]
    invalidation: dict[str, object]
    expiration: dict[str, object]
    risk_fraction: Decimal = Field(gt=0, le=Decimal("0.02"))


class StrategyCommand(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    instrument_id: UUID
    definition: StrategyDefinitionCommand
    change_summary: str = Field(
        default="Initial deterministic draft", min_length=8, max_length=2000
    )


class StrategyVersionCommand(BaseModel):
    definition: StrategyDefinitionCommand
    change_summary: str = Field(min_length=8, max_length=2000)


class ResearchJobCommand(BaseModel):
    purpose: str = Field(min_length=3, max_length=128)
    inputs: dict[str, object] = Field(default_factory=dict)
    parameters: dict[str, object] = Field(default_factory=dict)


class StrategyResearchModelCommand(BaseModel):
    model_alias: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$"
    )


class StrategyIdeaCommand(StrategyResearchModelCommand):
    instrument_id: UUID
    description: str = Field(min_length=16, max_length=4000)


def _actor(context: AuthenticationContext) -> Actor:
    return Actor(
        role=Role(context.user.role), assurance=context.session.assurance, id=context.user.id
    )


@router.get("")
def list_strategies(database: DatabaseSession) -> dict[str, object]:
    strategies = database.scalars(select(Strategy).order_by(Strategy.created_at.desc())).all()
    return {"items": [strategy_payload(database, strategy) for strategy in strategies]}


@router.post("/ai-research", status_code=202)
def start_ai_strategy_research(
    payload: StrategyResearchModelCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    """Queue one bounded AI strategy-selection proposal per active category."""

    from traderx.identity.authorization import require_role
    from traderx.shared.types import InvalidTransition

    require_role(_actor(context), {Role.OWNER, Role.ADMIN}, "strategy.ai-research", require_mfa=True)
    rows = database.execute(
        select(ActiveMarketAssignment, Instrument, CandidateAssessment)
        .join(Instrument, Instrument.id == ActiveMarketAssignment.instrument_id)
        .join(CandidateAssessment, CandidateAssessment.id == ActiveMarketAssignment.candidate_assessment_id)
        .where(
            ActiveMarketAssignment.state == AssignmentState.ACTIVE,
            ActiveMarketAssignment.effective_to.is_(None),
        )
        .order_by(ActiveMarketAssignment.category)
    ).all()
    categories = {assignment.category for assignment, _instrument, _candidate in rows}
    required = {"FOREX", "COMMODITY", "CRYPTO"}
    if categories != required:
        missing = ", ".join(sorted(required.difference(categories))) or "a single active market per category"
        raise InvalidTransition(
            "AI strategy research requires active Forex, Commodity, and Crypto markets; "
            f"missing {missing}"
        )
    model = database.scalar(
        select(MarketResearchModelConfiguration).where(
            MarketResearchModelConfiguration.scope == "GLOBAL"
        )
    )
    integration = database.get(Integration, model.llm_integration_id) if model else None
    if model is None or integration is None or integration.state != "HEALTHY":
        raise InvalidTransition("configure a healthy Market Research model before AI strategy research")
    active_markets = [
        {
            "assignment_id": str(assignment.id),
            "instrument_id": str(instrument.id),
            "symbol": instrument.symbol,
            "category": assignment.category,
            "market_evidence": {
                "score": str(candidate.score) if candidate.score is not None else None,
                "rank": candidate.rank,
                "confidence": str(candidate.confidence),
                "components": candidate.components,
                "eligibility_reason_codes": candidate.gate_evidence.get("reason_codes", []),
                "source_evidence": candidate.source_evidence,
            },
        }
        for assignment, instrument, candidate in rows
    ]
    pin = {
        "llm_integration_id": str(model.llm_integration_id),
        "provider_key": model.provider_key,
        "exact_model_id": payload.model_alias.strip(),
        "catalogue_revision": model.catalogue_revision,
        "adapter_revision": model.adapter_revision,
        "research_brief": model.research_brief,
        "model_prompt_profile": model_prompt_profile(integration.configuration, payload.model_alias.strip()),
    }
    job, detail = create_research_job(
        database,
        owner_id=context.user.id,
        request=ResearchRequest(
            "AI_ACTIVE_MARKET_STRATEGY_SELECTION",
            {"active_markets": active_markets},
            {"llm": pin, "requested_by": str(context.user.id)},
        ),
    )
    database.commit()
    try:
        from traderx_worker.runtime.celery_app import celery_app

        celery_app.send_task(
            "traderx.research.ai_strategy_selection",
            kwargs={"job_id": str(job.id)},
            queue="research",
        )
    except Exception as exc:
        raise RuntimeError("TraderX could not queue AI strategy research") from exc
    location = f"/api/v1/strategies/ai-research/{job.id}"
    response.headers["Location"] = location
    response.headers["Idempotency-Key"] = idempotency_key
    return {
        "job": {"id": str(job.id), "state": job.state},
        "research_detail_id": str(detail.id),
        "model_alias": payload.model_alias.strip(),
        "active_markets": [
            {"symbol": item["symbol"], "category": item["category"]} for item in active_markets
        ],
        "status_url": location,
    }


@router.post("/ai-research/from-idea", status_code=202)
def develop_strategy_idea(
    payload: StrategyIdeaCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    """Turn an owner's plain-language strategy idea into one bounded AI proposal."""

    from traderx.identity.authorization import require_role
    from traderx.shared.types import InvalidTransition

    require_role(_actor(context), {Role.OWNER, Role.ADMIN}, "strategy.ai-idea-research", require_mfa=True)
    row = database.execute(
        select(ActiveMarketAssignment, Instrument, CandidateAssessment)
        .join(Instrument, Instrument.id == ActiveMarketAssignment.instrument_id)
        .join(CandidateAssessment, CandidateAssessment.id == ActiveMarketAssignment.candidate_assessment_id)
        .where(
            ActiveMarketAssignment.instrument_id == payload.instrument_id,
            ActiveMarketAssignment.state == AssignmentState.ACTIVE,
            ActiveMarketAssignment.effective_to.is_(None),
        )
        .limit(1)
    ).first()
    if row is None:
        raise InvalidTransition("choose an active market before developing a strategy idea")
    assignment, instrument, candidate = row
    model = database.scalar(
        select(MarketResearchModelConfiguration).where(
            MarketResearchModelConfiguration.scope == "GLOBAL"
        )
    )
    integration = database.get(Integration, model.llm_integration_id) if model else None
    if model is None or integration is None or integration.state != "HEALTHY":
        raise InvalidTransition("configure a healthy Market Research model before developing a strategy idea")
    active_market = {
        "assignment_id": str(assignment.id),
        "instrument_id": str(instrument.id),
        "symbol": instrument.symbol,
        "category": assignment.category,
        "research_mode": "MANUAL_IDEA",
        "market_evidence": {
            "score": str(candidate.score) if candidate.score is not None else None,
            "rank": candidate.rank,
            "confidence": str(candidate.confidence),
            "components": candidate.components,
            "eligibility_reason_codes": candidate.gate_evidence.get("reason_codes", []),
            "source_evidence": candidate.source_evidence,
        },
    }
    pin = {
        "llm_integration_id": str(model.llm_integration_id),
        "provider_key": model.provider_key,
        "exact_model_id": payload.model_alias.strip(),
        "catalogue_revision": model.catalogue_revision,
        "adapter_revision": model.adapter_revision,
        "research_brief": model.research_brief,
        "model_prompt_profile": model_prompt_profile(integration.configuration, payload.model_alias.strip()),
    }
    job, detail = create_research_job(
        database,
        owner_id=context.user.id,
        request=ResearchRequest(
            "AI_STRATEGY_IDEA_REFINEMENT",
            {
                "active_markets": [active_market],
                "manual_strategy_description": payload.description.strip(),
            },
            {"llm": pin, "requested_by": str(context.user.id)},
        ),
    )
    database.commit()
    try:
        from traderx_worker.runtime.celery_app import celery_app

        celery_app.send_task(
            "traderx.research.ai_strategy_selection",
            kwargs={"job_id": str(job.id)},
            queue="research",
        )
    except Exception as exc:
        raise RuntimeError("TraderX could not queue AI strategy idea research") from exc
    location = f"/api/v1/strategies/ai-research/{job.id}"
    response.headers["Location"] = location
    response.headers["Idempotency-Key"] = idempotency_key
    return {
        "job": {"id": str(job.id), "state": job.state},
        "research_detail_id": str(detail.id),
        "model_alias": payload.model_alias.strip(),
        "active_market": {"symbol": instrument.symbol, "category": assignment.category},
        "status_url": location,
    }


@router.get("/ai-research/latest")
def latest_ai_strategy_research(
    context: Operator,
    database: DatabaseSession,
) -> dict[str, object]:
    """Return the most recent retained AI strategy research result for this workspace."""

    query = (
        select(BackgroundJob, ResearchJobDetail)
        .join(ResearchJobDetail, ResearchJobDetail.job_id == BackgroundJob.id)
        .where(BackgroundJob.job_type == "STRATEGY_RESEARCH")
        .order_by(ResearchJobDetail.created_at.desc())
    )
    if Role(context.user.role) not in {Role.OWNER, Role.ADMIN}:
        query = query.where(BackgroundJob.owner_id == context.user.id)
    row = database.execute(query.limit(1)).first()
    if row is None:
        return {"job": None, "result": None}
    job, detail = row
    return {
        "job": {
            "id": str(job.id),
            "state": job.state,
            "progress": job.progress,
            "error_code": job.error_code,
            "created_at": job.created_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        },
        "result": _strategy_research_result_payload(database, detail.result_summary),
    }


@router.get("/ai-research/{job_id}")
def get_ai_strategy_research(
    job_id: UUID,
    context: Operator,
    database: DatabaseSession,
) -> dict[str, object]:
    from traderx.shared.types import InvalidTransition

    job = database.get(BackgroundJob, job_id)
    detail = database.scalar(select(ResearchJobDetail).where(ResearchJobDetail.job_id == job_id))
    if job is None or detail is None or job.job_type != "STRATEGY_RESEARCH":
        raise InvalidTransition("the AI strategy research job does not exist")
    if job.owner_id != context.user.id and Role(context.user.role) not in {Role.OWNER, Role.ADMIN}:
        raise InvalidTransition("the AI strategy research job is not available to this user")
    return {
        "job": {
            "id": str(job.id),
            "state": job.state,
            "progress": job.progress,
            "error_code": job.error_code,
            "created_at": job.created_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        },
        "result": _strategy_research_result_payload(database, detail.result_summary),
    }


def _strategy_research_result_payload(
    database: Session, result_summary: dict[str, object] | None
) -> dict[str, object] | None:
    """Enrich pre-blueprint retained reports from their immutable draft rules."""

    if not isinstance(result_summary, dict):
        return result_summary
    payload = dict(result_summary)
    outcomes = payload.get("outcomes")
    if not isinstance(outcomes, list):
        return payload
    enriched: list[object] = []
    for raw_outcome in outcomes:
        if not isinstance(raw_outcome, dict) or raw_outcome.get("strategy_blueprint"):
            enriched.append(raw_outcome)
            continue
        try:
            version = database.get(StrategyVersion, UUID(str(raw_outcome["strategy_version_id"])))
            selection = validate_selection(raw_outcome["selection"])
            if version is None:
                raise ValueError("strategy version not retained")
            outcome = dict(raw_outcome)
            outcome["strategy_blueprint"] = strategy_blueprint_for(
                selection, definition_from_payload(version.definition)
            )
            enriched.append(outcome)
        except (KeyError, TypeError, ValueError):
            # Historical reports remain readable even if their immutable version
            # has been pruned or predates the research-selection contract.
            enriched.append(raw_outcome)
    payload["outcomes"] = enriched
    return payload


@router.post("", status_code=201)
def create_strategy(
    payload: StrategyCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    strategy, version = create_strategy_with_version(
        database,
        _actor(context),
        name=payload.name,
        instrument_id=payload.instrument_id,
        definition_payload=payload.definition.model_dump(mode="json"),
        change_summary=payload.change_summary,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
    )
    database.commit()
    database.refresh(strategy)
    response.headers["ETag"] = f'"strategy-{strategy.id}-{strategy.version}"'
    return {
        **strategy_payload(database, strategy),
        "created_version": strategy_version_payload(version),
    }


@router.post("/{strategy_id}/versions", status_code=201)
def create_strategy_version(
    strategy_id: UUID,
    payload: StrategyVersionCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    version = create_immutable_version(
        database,
        _actor(context),
        strategy_id=strategy_id,
        expected_etag=if_match,
        definition_payload=payload.definition.model_dump(mode="json"),
        change_summary=payload.change_summary,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
    )
    database.commit()
    database.refresh(version)
    response.headers["ETag"] = f'"strategy-version-{version.id}-{version.version}"'
    return strategy_version_payload(version)


@router.get("/{strategy_id}/versions/{sequence}")
def strategy_version(
    strategy_id: UUID,
    sequence: int,
    response: Response,
    database: DatabaseSession,
) -> dict[str, object]:
    version = database.scalar(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == strategy_id,
            StrategyVersion.sequence == sequence,
        )
    )
    if version is None:
        from traderx.shared.types import InvalidTransition

        raise InvalidTransition("the requested immutable strategy version does not exist")
    response.headers["ETag"] = f'"strategy-version-{version.id}-{version.version}"'
    return strategy_version_payload(version)


@router.get("/{strategy_id}/versions")
def strategy_versions(strategy_id: UUID, database: DatabaseSession) -> dict[str, object]:
    versions = database.scalars(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.sequence.desc())
    ).all()
    return {"items": [strategy_version_payload(version) for version in versions]}


@research_router.post("", status_code=202)
def start_strategy_research(
    payload: ResearchJobCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    job, detail = create_research_job(
        database,
        owner_id=context.user.id,
        request=ResearchRequest(payload.purpose, payload.inputs, payload.parameters),
    )
    database.commit()
    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    response.headers["Idempotency-Key"] = idempotency_key
    return {
        "job": {"id": str(job.id), "state": job.state},
        "research_detail_id": str(detail.id),
        "manifest_hash": job.input_manifest["hash"],
    }


@research_router.get("/{job_id}")
def research_job(job_id: UUID, database: DatabaseSession) -> dict[str, object]:
    detail = database.scalar(select(ResearchJobDetail).where(ResearchJobDetail.job_id == job_id))
    if detail is None:
        from traderx.shared.types import InvalidTransition

        raise InvalidTransition("the requested research job does not exist")
    return {
        "id": str(detail.id),
        "job_id": str(detail.job_id),
        "purpose": detail.purpose,
        "input_manifest": detail.input_manifest,
        "result_summary": detail.result_summary,
        "created_at": detail.created_at.isoformat(),
    }
