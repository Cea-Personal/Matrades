from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.model import Integration
from traderx.integrations.registry import approved_provider
from traderx.jobs.model import BackgroundJob, JobState
from traderx.market_data.mapping import approve_symbol_mapping
from traderx.market_data.model import Instrument
from traderx.market_research.configuration import (
    configure_model,
    configure_schedule,
    model_configuration_etag,
    model_configuration_payload,
    schedule_etag,
    schedule_payload,
)
from traderx.market_research.coordinator import coordinated_report, create_coordinated_run
from traderx.market_research.events import (
    LLM_ANALYSIS_RETRY_REQUESTED,
    emit_market_research_fact,
)
from traderx.market_research.model import (
    CoordinatedMarketResearchRun,
    MarketResearchModelConfiguration,
    MarketResearchRun,
    MarketResearchSchedule,
)
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
from traderx.shared.idempotency import (
    IdempotencyRecord,
    canonical_request_hash,
    complete,
    start_or_replay,
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


class ResearchScheduleCommand(BaseModel):
    account_id: UUID
    interval_seconds: int = Field(ge=3600, le=2592000)
    anchored_start_local: datetime
    account_timezone: str = Field(min_length=1, max_length=128)
    enabled: bool
    reason: str = Field(min_length=8, max_length=2000)


class ResearchModelCommand(BaseModel):
    llm_integration_id: UUID
    provider_key: str = Field(min_length=1, max_length=128)
    exact_model_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$"
    )
    reason: str = Field(min_length=8, max_length=2000)


class CoordinatedResearchCommand(BaseModel):
    account_id: UUID
    methodology_version: str = Field(default="market-suitability-v2", min_length=1)


class SymbolMappingCommand(BaseModel):
    integration_id: UUID
    provider_symbol: str = Field(min_length=1, max_length=256)
    venue: str = Field(min_length=1, max_length=128)
    mapping_revision: str = Field(default="owner-mapping-v1", min_length=1, max_length=64)
    contract_variant: str | None = Field(default=None, min_length=1, max_length=128)
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


@router.put("/instruments/{instrument_id}/mapping")
def put_instrument_mapping(
    instrument_id: UUID,
    payload: SymbolMappingCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    actor = _actor(context)
    require_role(actor, {Role.OWNER}, "market.mapping.approve", require_mfa=True)
    request_hash = canonical_request_hash(
        {
            "instrument_id": instrument_id,
            "if_match": if_match,
            **payload.model_dump(mode="json"),
        }
    )
    idempotency = database.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == context.user.id,
            IdempotencyRecord.operation == "market.mapping.approve",
            IdempotencyRecord.key == idempotency_key,
        )
    )
    replay = start_or_replay(idempotency, request_hash)
    if replay is not None:
        replay_etag = replay.get("etag")
        resource = replay.get("resource")
        if isinstance(replay_etag, str):
            response.headers["ETag"] = replay_etag
        if not isinstance(resource, dict):
            from traderx.shared.types import InvalidTransition

            raise InvalidTransition("the idempotent mapping result is no longer available")
        return {str(key): value for key, value in resource.items()}
    if idempotency is None:
        idempotency = IdempotencyRecord(
            actor_id=context.user.id,
            operation="market.mapping.approve",
            key=idempotency_key,
            request_hash=request_hash,
        )
        database.add(idempotency)
        database.flush()
    instrument = database.get(Instrument, instrument_id)
    integration = database.get(Integration, payload.integration_id)
    if instrument is None or integration is None:
        from traderx.shared.types import InvalidTransition

        raise InvalidTransition("the instrument or specialist integration does not exist")
    if if_match != f'"instrument-{instrument.id}-{instrument.version}"':
        from traderx.shared.types import ConcurrentModification

        raise ConcurrentModification("the instrument changed; refresh before approving its mapping")
    definition = approved_provider(integration.provider)
    if (
        integration.state != "HEALTHY"
        or integration.provider != definition.provider
        or instrument.category not in definition.asset_categories
        or (
            definition.entitlement_required
            and integration.entitlement_status != "VERIFIED"
        )
    ):
        from traderx.shared.types import InvalidTransition

        raise InvalidTransition("the specialist is not healthy and entitled for this category")
    try:
        alias = approve_symbol_mapping(
            database,
            actor,
            instrument=instrument,
            integration_id=integration.id,
            provider=integration.provider,
            provider_symbol=payload.provider_symbol,
            venue=payload.venue,
            catalogue_revision=integration.catalogue_revision or definition.catalogue_revision,
            mapping_revision=payload.mapping_revision,
            contract_variant=payload.contract_variant,
            reason=payload.reason,
            now=utc_now(),
            correlation_id=correlation_id.get() or "unavailable",
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        from traderx.shared.types import InvalidTransition

        raise InvalidTransition(str(exc)) from exc
    database.flush()
    etag = f'"instrument-{instrument.id}-{instrument.version}"'
    body: dict[str, object] = {
        "id": str(alias.id),
        "instrument_id": str(instrument.id),
        "provider": alias.provider,
        "provider_symbol": alias.native_symbol,
        "venue": alias.venue,
        "mapping_revision": alias.mapping_revision,
        "contract_variant": alias.contract_variant,
        "status": "APPROVED",
    }
    complete(
        idempotency,
        status=200,
        body={"resource": body, "etag": etag},
        completed_at=utc_now(),
    )
    database.commit()
    response.headers["ETag"] = etag
    return body


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


@router.get("/research/schedule")
def get_research_schedule(response: Response, database: DatabaseSession) -> dict[str, object]:
    schedule = database.scalar(select(MarketResearchSchedule).limit(1))
    response.headers["ETag"] = schedule_etag(schedule)
    return schedule_payload(schedule) if schedule else {"configured": False, "enabled": False}


@router.put("/research/schedule")
def put_research_schedule(
    payload: ResearchScheduleCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    schedule = configure_schedule(
        database,
        _actor(context),
        account_id=payload.account_id,
        interval_seconds=payload.interval_seconds,
        anchored_start_local=payload.anchored_start_local,
        account_timezone=payload.account_timezone,
        enabled=payload.enabled,
        reason=payload.reason,
        expected_etag=if_match,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
        now=utc_now(),
    )
    database.commit()
    database.refresh(schedule)
    response.headers["ETag"] = schedule_etag(schedule)
    return schedule_payload(schedule)


@router.get("/research/model-configuration")
def get_research_model_configuration(
    response: Response, database: DatabaseSession
) -> dict[str, object]:
    configuration = database.scalar(
        select(MarketResearchModelConfiguration).where(
            MarketResearchModelConfiguration.scope == "GLOBAL"
        )
    )
    response.headers["ETag"] = model_configuration_etag(configuration)
    return (
        model_configuration_payload(configuration)
        if configuration
        else {"configured": False, "applies_to": "FUTURE_RUNS_ONLY"}
    )


@router.put("/research/model-configuration")
def put_research_model_configuration(
    payload: ResearchModelCommand,
    context: Operator,
    database: DatabaseSession,
    response: Response,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    configuration = configure_model(
        database,
        _actor(context),
        llm_integration_id=payload.llm_integration_id,
        provider_key=payload.provider_key,
        exact_model_id=payload.exact_model_id,
        reason=payload.reason,
        expected_etag=if_match,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id.get() or "unavailable",
        now=utc_now(),
    )
    database.commit()
    database.refresh(configuration)
    response.headers["ETag"] = model_configuration_etag(configuration)
    return model_configuration_payload(configuration)


@router.post("/research/coordinated", status_code=202)
def start_coordinated_research(
    payload: CoordinatedResearchCommand,
    context: Operator,
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    actor = _actor(context)
    require_role(actor, {Role.OWNER}, "market-research.coordinated.start", require_mfa=True)
    prior = database.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "market-research.coordinated.start",
            AuditEvent.idempotency_key == idempotency_key,
            AuditEvent.actor_id == context.user.id,
        )
    )
    if prior is not None and prior.target_id is not None:
        existing = database.get(CoordinatedMarketResearchRun, prior.target_id)
        if existing is not None:
            return {
                "run_id": str(existing.id),
                "state": existing.state,
                "category_count": 3,
                "idempotency_key": idempotency_key,
            }
    configuration = database.scalar(
        select(MarketResearchModelConfiguration).where(
            MarketResearchModelConfiguration.scope == "GLOBAL"
        )
    )
    llm_pin: dict[str, object] | None = None
    if configuration is not None:
        llm_pin = {
            "llm_integration_id": configuration.llm_integration_id,
            "provider_key": configuration.provider_key,
            "exact_model_id": configuration.exact_model_id,
            "catalogue_revision": configuration.catalogue_revision,
            "adapter_revision": configuration.adapter_revision,
            "prompt_template_version": configuration.prompt_template_version,
            "output_schema_version": configuration.output_schema_version,
            "inference_policy_version": configuration.inference_policy_version,
        }
    run = create_coordinated_run(
        database,
        account_id=payload.account_id,
        trigger="MANUAL",
        methodology_version=payload.methodology_version,
        source_catalogue_revision="2026-08-14.v1",
        freshness_policy_manifest={"default": "freshness-2026-08-v1"},
        retry_policy_manifest={"default": "retry-2026-08-v1"},
        now=utc_now(),
        llm_pin=llm_pin,
    )
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=context.user.id,
            actor_role=context.user.role,
            action="market-research.coordinated.start",
            outcome="SUCCEEDED",
            target_type="coordinated_market_research_run",
            target_id=run.id,
            target_version=run.version,
            reason="Run all three governed market categories",
            assurance=context.session.assurance,
            correlation_id=correlation_id.get() or "unavailable",
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=None,
            new_value={"state": run.state, "category_count": 3},
            occurred_at=utc_now(),
        )
    )
    database.commit()
    return {
        "run_id": str(run.id),
        "state": run.state,
        "category_count": 3,
        "idempotency_key": idempotency_key,
    }


@router.get("/research/coordinated")
def list_coordinated_research(
    database: DatabaseSession,
    account_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    statement = select(CoordinatedMarketResearchRun).order_by(
        CoordinatedMarketResearchRun.created_at.desc()
    )
    if account_id is not None:
        statement = statement.where(CoordinatedMarketResearchRun.account_id == account_id)
    parents = list(database.scalars(statement.limit(limit)))
    return {"items": [coordinated_report(database, parent.id) for parent in parents]}


@router.get("/research/coordinated/{run_id}")
def get_coordinated_research(run_id: UUID, database: DatabaseSession) -> dict[str, object]:
    return coordinated_report(database, run_id)


@router.post("/research/category-runs/{run_id}/llm-analysis/retry", status_code=202)
def retry_category_analysis(
    run_id: UUID,
    context: Operator,
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    actor = _actor(context)
    require_role(actor, {Role.OWNER}, "market-research.llm.retry", require_mfa=True)
    run = database.get(MarketResearchRun, run_id)
    if run is None:
        from traderx.shared.types import InvalidTransition

        raise InvalidTransition("the requested category research run does not exist")
    run.llm_analysis_state = "RETRY_QUEUED"
    now = utc_now()
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=context.user.id,
            actor_role=context.user.role,
            action="market-research.llm.retry",
            outcome="SUCCEEDED",
            target_type="market_research_run",
            target_id=run.id,
            target_version=run.version,
            reason="Retry advisory analysis with the original model pin",
            assurance=context.session.assurance,
            correlation_id=correlation_id.get() or "unavailable",
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value={"llm_analysis_state": "UNAVAILABLE"},
            new_value={"llm_analysis_state": "RETRY_QUEUED"},
            occurred_at=now,
        )
    )
    emit_market_research_fact(
        database,
        aggregate_type="market_research_run",
        aggregate_id=run.id,
        aggregate_version=run.version,
        event_type=LLM_ANALYSIS_RETRY_REQUESTED,
        data={
            "category": run.category,
            "coordinated_run_id": str(run.coordinated_run_id),
            "same_pinned_model": True,
            "requested_by": str(context.user.id),
        },
        now=now,
        correlation_id=correlation_id.get() or "unavailable",
        actor_id=context.user.id,
    )
    database.commit()
    return {
        "run_id": str(run.id),
        "state": run.llm_analysis_state,
        "same_pinned_model": True,
        "requested_by": str(context.user.id),
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
