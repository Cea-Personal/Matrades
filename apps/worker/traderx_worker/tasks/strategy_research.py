from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import httpx
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.identity.authorization import Actor, Role
from traderx.integrations.crypto import EncryptedSecret, SecretBox
from traderx.integrations.model import CredentialVersion, Integration
from traderx.integrations.llm_profiles import with_owner_system_message
from traderx.integrations.ports import LlmAnalysisPort, LlmAnalysisRequest
from traderx.integrations.providers.anthropic_messages import AnthropicMessagesAdapter
from traderx.integrations.providers.litellm_proxy import LiteLlmProxyAdapter
from traderx.integrations.providers.openai_responses import OpenAIResponsesAdapter
from traderx.jobs.model import BackgroundJob, JobState
from traderx.market_data.model import Instrument
from traderx.market_research.model import ActiveMarketAssignment, AssignmentState
from traderx.research.model import ResearchJobDetail
from traderx.research.service import record_experiment
from traderx.shared.config import get_settings
from traderx.shared.types import as_decimal, utc_now
from traderx.strategies.ai_research import (
    INFERENCE_POLICY_VERSION,
    OUTPUT_SCHEMA_VERSION,
    PROMPT_TEMPLATE_VERSION,
    selection_json_schema,
    strategy_blueprint_for,
    strategy_definition_for,
    system_instruction,
    validate_selection,
)
from traderx.strategies.compiler import compile_strategy
from traderx.strategies.lifecycle import create_immutable_version, create_strategy_with_version
from traderx.strategies.model import Strategy, StrategyVersion
from traderx.strategies.schema import StrategyDefinition
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.research.ai_strategy_selection", bind=True, acks_late=True)
def research_active_market_strategies(self: object, job_id: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Ask the pinned advisory model to select a reviewed strategy family per active market.

    The model never supplies an executable strategy definition. Its selection is
    compiled into a small deterministic template catalogue, then saved as an
    immutable DRAFT which still requires backtesting, validation, paper trading,
    and human approvals before it can affect an opportunity.
    """

    with session_factory().begin() as database:
        job = database.get(BackgroundJob, UUID(job_id))
        detail = database.scalar(select(ResearchJobDetail).where(ResearchJobDetail.job_id == UUID(job_id)))
        if job is None or detail is None:
            return {"job_id": job_id, "status": "NOT_FOUND"}
        if JobState(job.state or JobState.QUEUED) == JobState.QUEUED:
            job.transition(JobState.RUNNING)
            job.started_at = utc_now()
            job.attempt_count += 1
        if JobState(job.state) != JobState.RUNNING:
            return {"job_id": job_id, "status": str(job.state)}

        inputs = detail.input_manifest.get("inputs", {})
        parameters = detail.input_manifest.get("parameters", {})
        active_markets = inputs.get("active_markets", []) if isinstance(inputs, dict) else []
        strategy_idea = inputs.get("manual_strategy_description") if isinstance(inputs, dict) else None
        llm_pin = parameters.get("llm", {}) if isinstance(parameters, dict) else {}
        if not isinstance(active_markets, list) or not isinstance(llm_pin, dict):
            return _fail(job, detail, "INVALID_RESEARCH_MANIFEST")
        port = _analysis_port(database, llm_pin)
        if port is None:
            return _fail(job, detail, "MODEL_NOT_HEALTHY_OR_CONFIGURED")

        outcomes: list[dict[str, object]] = []
        try:
            for index, item in enumerate(active_markets, start=1):
                if not isinstance(item, dict):
                    continue
                outcome = _research_one(
                    database,
                    job,
                    item,
                    llm_pin,
                    port,
                    strategy_idea=strategy_idea if isinstance(strategy_idea, str) else None,
                )
                outcomes.append(outcome)
                record_experiment(
                    database,
                    research_detail_id=detail.id,
                    parameters={
                        "research_job_id": str(detail.id),
                        "instrument_id": item.get("instrument_id"),
                        "category": item.get("category"),
                    },
                    outcome="ACCEPTED" if outcome["state"] == "PROPOSED" else "FAILED",
                )
                job.progress = {
                    "completed_units": index,
                    "total_units": len(active_markets),
                    "message": f"Researched {item.get('symbol', 'active market')}",
                }
            detail.result_summary = {
                "state": "COMPLETED",
                "selection_policy": "AI selects an approved family; TraderX compiles deterministic templates",
                "manual_strategy_description": strategy_idea if isinstance(strategy_idea, str) else None,
                "outcomes": outcomes,
            }
            job.transition(JobState.COMPLETED)
            job.finished_at = utc_now()
            job.result_ref = f"/api/v1/strategies/ai-research/{job.id}"
            job.progress = {"completed_units": len(outcomes), "total_units": len(active_markets), "message": "Completed"}
            return {"job_id": job_id, "status": "COMPLETED", "outcomes": outcomes}
        finally:
            _close_port(port)


def _research_one(
    database: Session,
    job: BackgroundJob,
    item: dict[str, object],
    llm_pin: dict[str, object],
    port: LlmAnalysisPort,
    *,
    strategy_idea: str | None,
) -> dict[str, object]:
    instrument_id = _uuid(item.get("instrument_id"))
    instrument = database.get(Instrument, instrument_id) if instrument_id else None
    if instrument is None or not _still_active(database, instrument, str(item.get("category", ""))):
        return {"symbol": item.get("symbol", "UNKNOWN"), "state": "STALE_ACTIVE_MARKET"}
    try:
        price = _current_price(instrument)
    except (TypeError, ValueError):
        return {"symbol": instrument.symbol, "state": "PRICE_UNAVAILABLE"}
    if price is None:
        return {"symbol": instrument.symbol, "state": "PRICE_UNAVAILABLE"}
    request = LlmAnalysisRequest(
        provider=str(llm_pin["provider_key"]),
        exact_model_id=str(llm_pin["exact_model_id"]),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        output_schema_version=OUTPUT_SCHEMA_VERSION,
        inference_policy_version=INFERENCE_POLICY_VERSION,
        evidence={
            "instrument": {
                "symbol": instrument.symbol,
                "category": instrument.category,
                "current_price": str(price),
                "recent_closes": _recent_closes(instrument),
                "trading_hours": instrument.trading_hours,
                "market_evidence": item.get("market_evidence", {}),
            },
            "research_brief": llm_pin.get("research_brief"),
            "owner_strategy_idea": strategy_idea,
            "selection_constraint": "Select one approved family only; no execution or custom rules.",
        },
        store=False,
        output_schema_name="strategy_selection",
        output_schema=selection_json_schema(),
        system_instruction=with_owner_system_message(
            system_instruction(), _prompt_message(llm_pin, "system_message")
        ),
        user_instruction=_prompt_message(llm_pin, "user_message"),
    )
    try:
        response = port.analyze(request)
    except Exception:
        return {"symbol": instrument.symbol, "state": "MODEL_UNAVAILABLE", "reason": "PROVIDER_FAILURE"}
    if response.state != "COMPLETED" or response.analysis is None:
        return {
            "symbol": instrument.symbol,
            "state": "MODEL_UNAVAILABLE",
            "reason": response.reason or response.state,
        }
    try:
        selection = validate_selection(response.analysis)
        definition = strategy_definition_for(selection, price=price)
    except Exception:
        return {"symbol": instrument.symbol, "state": "MODEL_OUTPUT_INVALID"}
    return _save_proposal(
        database,
        job,
        instrument,
        selection.model_dump(mode="json"),
        definition,
        strategy_blueprint_for(selection, definition),
        strategy_idea=bool(strategy_idea),
    )


def _save_proposal(
    database: Session,
    job: BackgroundJob,
    instrument: Instrument,
    selection: dict[str, object],
    definition: StrategyDefinition,
    blueprint: dict[str, object],
    *,
    strategy_idea: bool,
) -> dict[str, object]:
    name = f"AI strategy idea · {instrument.symbol}" if strategy_idea else f"AI strategy · {instrument.symbol}"
    strategy = database.scalar(select(Strategy).where(Strategy.name == name).with_for_update())
    actor = Actor(role=Role.OWNER, assurance="MFA", id=job.owner_id)
    prefix = "AI elaborated the owner strategy idea" if strategy_idea else "AI strategy research selected"
    change_summary = (
        f"{prefix} {selection['strategy_family']} {selection['direction']} for {instrument.symbol}: "
        f"{selection['rationale']}"
    )[:2000]
    # The lifecycle boundary accepts JSON-compatible list values; dataclasses
    # preserves tuples in its canonical representation until this conversion.
    payload = json.loads(json.dumps(definition.canonical()))
    compiled = compile_strategy(definition)
    if strategy is None:
        strategy, version = create_strategy_with_version(
            database,
            actor,
            name=name,
            instrument_id=instrument.id,
            definition_payload=payload,
            change_summary=change_summary,
            idempotency_key=f"ai-strategy-{job.id}-{instrument.id}",
            correlation_id=f"ai-strategy-research-{job.id}",
        )
    else:
        latest = database.scalar(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy.id)
            .order_by(StrategyVersion.sequence.desc())
            .limit(1)
        )
        if latest is not None and latest.definition_hash == compiled.definition_hash:
            return {
                "symbol": instrument.symbol,
                "state": "UNCHANGED",
                "strategy_id": str(strategy.id),
                "strategy_version_id": str(latest.id),
                "selection": selection,
                "strategy_blueprint": blueprint,
            }
        version = create_immutable_version(
            database,
            actor,
            strategy_id=strategy.id,
            expected_etag=f'"strategy-{strategy.id}-{strategy.version}"',
            definition_payload=payload,
            change_summary=change_summary,
            idempotency_key=f"ai-strategy-{job.id}-{instrument.id}",
            correlation_id=f"ai-strategy-research-{job.id}",
        )
    return {
        "symbol": instrument.symbol,
        "category": instrument.category,
        "state": "PROPOSED",
        "strategy_id": str(strategy.id),
        "strategy_version_id": str(version.id),
        "selection": selection,
        "strategy_blueprint": blueprint,
        "lifecycle": version.lifecycle,
    }


def _analysis_port(database: Session, pin: dict[str, object]) -> LlmAnalysisPort | None:
    try:
        integration = database.get(Integration, UUID(str(pin["llm_integration_id"])))
    except (KeyError, ValueError):
        return None
    if integration is None or integration.state != "HEALTHY" or integration.provider != pin.get("provider_key"):
        return None
    credential_field = "virtual_key" if integration.provider == "LITELLM_PROXY" else "api_key"
    credentials = _credentials(database, integration)
    key = str(credentials.get(credential_field, ""))
    if not key:
        return None
    client = httpx.Client(timeout=get_settings().llm_attempt_timeout_seconds)
    if integration.provider == "OPENAI_RESPONSES":
        return OpenAIResponsesAdapter(key, client=client)
    if integration.provider == "ANTHROPIC_MESSAGES":
        return AnthropicMessagesAdapter(key, client=client)
    if integration.provider == "LITELLM_PROXY":
        return LiteLlmProxyAdapter(key, base_url=str(integration.configuration["base_url"]), client=client)
    client.close()
    return None


def _credentials(database: Session, integration: Integration) -> dict[str, object]:
    credential = database.scalar(
        select(CredentialVersion)
        .where(CredentialVersion.integration_id == integration.id, CredentialVersion.active.is_(True))
        .order_by(CredentialVersion.created_at.desc())
        .limit(1)
    )
    if credential is None:
        return {}
    encrypted = EncryptedSecret(**json.loads(credential.encrypted_value))
    return SecretBox(
        get_settings().encryption_key_b64.get_secret_value(), key_version=credential.key_version
    ).decrypt(encrypted)


def _still_active(database: Session, instrument: Instrument, category: str) -> bool:
    return database.scalar(
        select(ActiveMarketAssignment.id).where(
            ActiveMarketAssignment.instrument_id == instrument.id,
            ActiveMarketAssignment.category == category,
            ActiveMarketAssignment.state == AssignmentState.ACTIVE,
            ActiveMarketAssignment.effective_to.is_(None),
        )
    ) is not None


def _current_price(instrument: Instrument) -> Decimal | None:
    closes = instrument.contract_spec.get("closes")
    if isinstance(closes, list) and closes:
        return as_decimal(str(closes[-1]))
    bid, ask = instrument.contract_spec.get("bid"), instrument.contract_spec.get("ask")
    if bid is not None and ask is not None:
        return (as_decimal(str(bid)) + as_decimal(str(ask))) / Decimal("2")
    return None


def _recent_closes(instrument: Instrument) -> list[str]:
    closes = instrument.contract_spec.get("closes")
    if not isinstance(closes, list):
        return []
    return [str(value) for value in closes[-24:]]


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _prompt_message(pin: dict[str, object], key: str) -> str | None:
    profile = pin.get("model_prompt_profile")
    if not isinstance(profile, dict):
        return None
    value = profile.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _close_port(port: LlmAnalysisPort) -> None:
    client = getattr(port, "_client", None)
    if client is not None:
        client.close()


def _fail(job: BackgroundJob, detail: ResearchJobDetail, code: str) -> dict[str, object]:
    detail.result_summary = {"state": "FAILED", "reason": code, "outcomes": []}
    job.error_code = code
    job.transition(JobState.FAILED)
    job.finished_at = utc_now()
    job.progress = {"completed_units": 0, "total_units": 0, "message": code}
    return {"job_id": str(job.id), "status": "FAILED", "reason": code}
