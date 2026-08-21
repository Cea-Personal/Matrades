from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.model import Integration
from traderx.integrations.registry import approved_provider, validate_llm_model_id
from traderx.market_research.events import (
    MODEL_CONFIGURATION_CHANGED,
    SCHEDULE_CHANGED,
    emit_market_research_fact,
)
from traderx.market_research.llm_schema import (
    INFERENCE_POLICY_VERSION,
    OUTPUT_SCHEMA_VERSION,
    PROMPT_TEMPLATE_VERSION,
)
from traderx.market_research.model import (
    MarketResearchModelConfiguration,
    MarketResearchSchedule,
)
from traderx.market_research.scheduling import next_due_at
from traderx.shared.idempotency import (
    IdempotencyRecord,
    canonical_request_hash,
    complete,
    start_or_replay,
)
from traderx.shared.types import ConcurrentModification, InvalidTransition


def schedule_etag(schedule: MarketResearchSchedule | None) -> str:
    return f'"market-research-schedule-{schedule.version if schedule else 0}"'


def model_configuration_etag(configuration: MarketResearchModelConfiguration | None) -> str:
    return f'"market-research-model-{configuration.version if configuration else 0}"'


def configure_schedule(
    database: Session,
    actor: Actor,
    *,
    account_id: UUID,
    interval_seconds: int,
    anchored_start_local: datetime,
    account_timezone: str,
    enabled: bool,
    reason: str,
    expected_etag: str,
    idempotency_key: str,
    correlation_id: str,
    now: datetime,
) -> MarketResearchSchedule:
    require_role(actor, {Role.OWNER}, "market-research.schedule.configure", require_mfa=True)
    idempotency, replay_id = _start_configuration_request(
        database,
        actor,
        operation="market-research.schedule.configure",
        idempotency_key=idempotency_key,
        request={
            "account_id": account_id,
            "interval_seconds": interval_seconds,
            "anchored_start_local": anchored_start_local,
            "account_timezone": account_timezone,
            "enabled": enabled,
            "reason": reason,
            "expected_etag": expected_etag,
        },
    )
    if replay_id is not None:
        replay = database.get(MarketResearchSchedule, replay_id)
        if replay is None:
            raise InvalidTransition("the idempotent schedule result is no longer available")
        return replay
    current = database.scalar(
        select(MarketResearchSchedule).where(MarketResearchSchedule.account_id == account_id)
    )
    if expected_etag != schedule_etag(current):
        raise ConcurrentModification("the market research schedule changed; refresh and retry")
    due = (
        anchored_start_local
        if anchored_start_local > now
        else next_due_at(
            anchored_start_local=anchored_start_local,
            account_timezone=account_timezone,
            interval_seconds=interval_seconds,
            after=now,
        )
    )
    previous = _schedule_payload(current) if current else None
    if current is None:
        current = MarketResearchSchedule(
            account_id=account_id,
            interval_seconds=interval_seconds,
            anchored_start_local=anchored_start_local,
            account_timezone=account_timezone,
            enabled=enabled,
            next_run_at=due,
            changed_by=_actor_id(actor),
            change_reason=reason,
        )
        database.add(current)
    else:
        current.interval_seconds = interval_seconds
        current.anchored_start_local = anchored_start_local
        current.account_timezone = account_timezone
        current.enabled = enabled
        current.next_run_at = due
        current.changed_by = _actor_id(actor)
        current.change_reason = reason
    database.flush()
    current_payload = _schedule_payload(current)
    _audit(
        database,
        actor,
        action="market-research.schedule.configure",
        target_type="market_research_schedule",
        target_id=current.id,
        target_version=current.version,
        reason=reason,
        previous=previous,
        current=current_payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        now=now,
    )
    emit_market_research_fact(
        database,
        aggregate_type="market_research_schedule",
        aggregate_id=current.id,
        aggregate_version=current.version,
        event_type=SCHEDULE_CHANGED,
        data=current_payload,
        now=now,
        correlation_id=correlation_id,
        actor_id=actor.id,
    )
    complete(idempotency, status=200, body={"id": str(current.id)}, completed_at=now)
    return current


def configure_model(
    database: Session,
    actor: Actor,
    *,
    llm_integration_id: UUID,
    provider_key: str,
    exact_model_id: str,
    research_brief: str,
    reason: str,
    expected_etag: str,
    idempotency_key: str,
    correlation_id: str,
    now: datetime,
) -> MarketResearchModelConfiguration:
    require_role(actor, {Role.OWNER}, "market-research.model.configure", require_mfa=True)
    try:
        exact_model_id = validate_llm_model_id(provider_key, exact_model_id)
    except ValueError as exc:
        raise InvalidTransition(str(exc)) from exc
    research_brief = research_brief.strip()
    if len(research_brief) < 8:
        raise InvalidTransition("the research brief must contain at least 8 characters")
    idempotency, replay_id = _start_configuration_request(
        database,
        actor,
        operation="market-research.model.configure",
        idempotency_key=idempotency_key,
        request={
            "llm_integration_id": llm_integration_id,
            "provider_key": provider_key,
            "exact_model_id": exact_model_id,
            "research_brief": research_brief,
            "reason": reason,
            "expected_etag": expected_etag,
        },
    )
    if replay_id is not None:
        replay = database.get(MarketResearchModelConfiguration, replay_id)
        if replay is None:
            raise InvalidTransition("the idempotent model-selection result is no longer available")
        return replay
    current = database.scalar(
        select(MarketResearchModelConfiguration).where(
            MarketResearchModelConfiguration.scope == "GLOBAL"
        )
    )
    if expected_etag != model_configuration_etag(current):
        raise ConcurrentModification("the research model selection changed; refresh and retry")
    integration = database.get(Integration, llm_integration_id)
    if (
        integration is None
        or integration.category != "LLM"
        or integration.state not in {"HEALTHY", "ENABLED"}
        or integration.provider != provider_key
        or "LLM_ANALYSIS" not in integration.capabilities
    ):
        raise InvalidTransition("the selected LLM integration is not qualified and healthy")
    definition = approved_provider(provider_key)
    previous = _model_payload(current) if current else None
    values = {
        "llm_integration_id": integration.id,
        "provider_key": definition.provider,
        "exact_model_id": exact_model_id,
        "catalogue_revision": definition.catalogue_revision,
        "adapter_revision": definition.adapter_revision,
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "inference_policy_version": INFERENCE_POLICY_VERSION,
        "research_brief": research_brief,
        "effective_at": now,
        "changed_by": _actor_id(actor),
        "change_reason": reason,
    }
    if current is None:
        current = MarketResearchModelConfiguration(scope="GLOBAL", **values)
        database.add(current)
    else:
        for key, value in values.items():
            setattr(current, key, value)
    database.flush()
    current_payload = _model_payload(current)
    _audit(
        database,
        actor,
        action="market-research.model.configure",
        target_type="market_research_model_configuration",
        target_id=current.id,
        target_version=current.version,
        reason=reason,
        previous=previous,
        current=current_payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        now=now,
    )
    emit_market_research_fact(
        database,
        aggregate_type="market_research_model_configuration",
        aggregate_id=current.id,
        aggregate_version=current.version,
        event_type=MODEL_CONFIGURATION_CHANGED,
        data=current_payload,
        now=now,
        correlation_id=correlation_id,
        actor_id=actor.id,
    )
    complete(idempotency, status=200, body={"id": str(current.id)}, completed_at=now)
    return current


def _start_configuration_request(
    database: Session,
    actor: Actor,
    *,
    operation: str,
    idempotency_key: str,
    request: dict[str, object],
) -> tuple[IdempotencyRecord, UUID | None]:
    actor_id = _actor_id(actor)
    request_hash = canonical_request_hash(request)
    record = database.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == idempotency_key,
        )
    )
    replay = start_or_replay(record, request_hash)
    if record is not None:
        assert replay is not None
        return record, UUID(str(replay["id"]))
    record = IdempotencyRecord(
        actor_id=actor_id,
        operation=operation,
        key=idempotency_key,
        request_hash=request_hash,
    )
    database.add(record)
    database.flush()
    return record, None


def _schedule_payload(schedule: MarketResearchSchedule | None) -> dict[str, object]:
    if schedule is None:
        return {}
    return {
        "id": str(schedule.id),
        "account_id": str(schedule.account_id),
        "interval_seconds": schedule.interval_seconds,
        "anchored_start_local": schedule.anchored_start_local.isoformat(),
        "account_timezone": schedule.account_timezone,
        "enabled": schedule.enabled,
        "next_run_at": schedule.next_run_at.isoformat(),
        "last_due_at": schedule.last_due_at.isoformat() if schedule.last_due_at else None,
        "version": schedule.version,
    }


def _model_payload(
    configuration: MarketResearchModelConfiguration | None,
) -> dict[str, object]:
    if configuration is None:
        return {}
    return {
        "id": str(configuration.id),
        "llm_integration_id": str(configuration.llm_integration_id),
        "provider_key": configuration.provider_key,
        "exact_model_id": configuration.exact_model_id,
        "catalogue_revision": configuration.catalogue_revision,
        "adapter_revision": configuration.adapter_revision,
        "prompt_template_version": configuration.prompt_template_version,
        "output_schema_version": configuration.output_schema_version,
        "inference_policy_version": configuration.inference_policy_version,
        "research_brief": configuration.research_brief,
        "effective_at": configuration.effective_at.isoformat(),
        "version": configuration.version,
        "applies_to": "FUTURE_RUNS_ONLY",
    }


def schedule_payload(schedule: MarketResearchSchedule | None) -> dict[str, object]:
    return _schedule_payload(schedule)


def model_configuration_payload(
    configuration: MarketResearchModelConfiguration | None,
) -> dict[str, object]:
    return _model_payload(configuration)


def _actor_id(actor: Actor) -> UUID:
    if actor.id is None:
        raise ValueError("configuration actor must have an identifier")
    return actor.id


def _audit(
    database: Session,
    actor: Actor,
    *,
    action: str,
    target_type: str,
    target_id: UUID,
    target_version: int,
    reason: str,
    previous: dict[str, object] | None,
    current: dict[str, object],
    idempotency_key: str,
    correlation_id: str,
    now: datetime,
) -> None:
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=actor.id,
            actor_role=actor.role,
            action=action,
            outcome="SUCCEEDED",
            target_type=target_type,
            target_id=target_id,
            target_version=target_version,
            reason=reason,
            assurance=actor.assurance,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=previous,
            new_value=current,
            occurred_at=now,
        )
    )
