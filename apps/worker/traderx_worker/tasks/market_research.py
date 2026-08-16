from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

import httpx
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.integrations.crypto import EncryptedSecret, SecretBox
from traderx.integrations.model import CredentialVersion, FreshnessPolicyVersion, Integration
from traderx.integrations.ports import MarketDataCapability, SourceSemantics
from traderx.integrations.providers.anthropic_messages import AnthropicMessagesAdapter
from traderx.integrations.providers.openai_responses import OpenAIResponsesAdapter
from traderx.jobs.model import BackgroundJob, JobState
from traderx.market_data.model import Instrument, InstrumentAlias
from traderx.market_data.providers.cboe_fx_spot import CboeFxSpotAdapter
from traderx.market_data.providers.cme_group import CmeGroupAdapter
from traderx.market_data.providers.coinbase_exchange import CoinbaseExchangeAdapter
from traderx.market_data.providers.http import ProviderHttpTransport, ProviderTransportError
from traderx.market_data.source_evidence import (
    ConflictState,
    FreshnessPolicy,
    FreshnessState,
    SourceEvidence,
    SourceRole,
    build_source_evidence,
)
from traderx.market_research.coordinator import record_category_outcome
from traderx.market_research.llm_analysis import retry_advisory_analysis, run_advisory_analysis
from traderx.market_research.model import (
    CandidateAssessment,
    CoordinatedMarketResearchRun,
    MarketResearchRun,
)
from traderx.market_research.service import execute_market_research, refresh_mt5_instrument_catalog
from traderx.market_research.source_selection import (
    SourceAttempt,
    SourceSelection,
    select_market_source,
)
from traderx.shared.config import get_settings
from traderx.shared.types import InvalidTransition, utc_now
from traderx_worker.runtime.jobs import checkpoint
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.market_data.sync", bind=True, acks_late=True)
def synchronize_market_data(
    self: object,
    provider: str,
    cursor: str | None = None,
    background_job_id: str | None = None,
) -> dict[str, str | None]:
    if provider != "MT5_TERMINAL_BRIDGE":
        return {"provider": provider, "cursor": cursor, "status": "REJECTED_UNAPPROVED_PROVIDER"}
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if job is not None:
            checkpoint(
                job,
                completed=0,
                total=1,
                message="Refreshing the broker instrument catalog",
                now=utc_now(),
            )
            if job.state in {JobState.CANCELLED, JobState.PAUSED}:
                return {"provider": provider, "cursor": cursor, "status": str(job.state)}
        imported = refresh_mt5_instrument_catalog(database)
        if job is not None:
            checkpoint(
                job,
                completed=1,
                total=1,
                message="Broker instrument catalog refreshed",
                now=utc_now(),
            )
            job.transition(JobState.COMPLETED)
            job.finished_at = utc_now()
            job.result_ref = f"market-data:{provider}:{cursor or 'full'}"
    return {
        "provider": provider,
        "cursor": cursor,
        "status": "COMPLETED",
        "imported": str(imported),
    }


@shared_task(name="traderx.market_research.run", bind=True, acks_late=True)
def run_market_research(
    self: object, category: str, background_job_id: str | None = None
) -> dict[str, str]:
    with session_factory().begin() as database:
        job = _start_job(database, background_job_id)
        if job is not None:
            checkpoint(
                job,
                completed=0,
                total=2,
                message="Evaluating mandatory eligibility gates",
                now=utc_now(),
            )
            if job.state in {JobState.CANCELLED, JobState.PAUSED}:
                return {"category": category, "run_id": "", "status": str(job.state)}
        run = execute_market_research(
            database, category=category, method_version="market-suitability-v1"
        )
        run_id = str(run.id)
        if job is not None:
            checkpoint(
                job,
                completed=2,
                total=2,
                message="Immutable research report completed",
                now=utc_now(),
            )
            job.transition(JobState.COMPLETED)
            job.finished_at = utc_now()
            job.result_ref = f"/api/v1/markets/research/{run_id}"
    return {"category": category, "run_id": run_id, "status": "COMPLETED"}


@shared_task(name="traderx.market_research.dispatch_coordinated", acks_late=True)
def dispatch_coordinated_run(coordinated_run_id: str) -> dict[str, object]:
    """Dispatch exactly the three already-persisted category children."""

    with session_factory().begin() as database:
        parent = database.get(CoordinatedMarketResearchRun, UUID(coordinated_run_id))
        if parent is None:
            return {"run_id": coordinated_run_id, "status": "MISSING"}
        parent.state = "RUNNING"
        parent.started_at = parent.started_at or utc_now()
        children = list(
            database.scalars(
                select(MarketResearchRun)
                .where(MarketResearchRun.coordinated_run_id == parent.id)
                .order_by(MarketResearchRun.category)
            )
        )
        child_ids = [str(child.id) for child in children]
    for child_id in child_ids:
        run_coordinated_category.delay(child_id)
    return {"run_id": coordinated_run_id, "status": "DISPATCHED", "children": child_ids}


@shared_task(name="traderx.market_research.run_category", acks_late=True)
def run_coordinated_category(category_run_id: str) -> dict[str, str]:
    """Idempotently evaluate one child; ranking never changes an active assignment."""

    with session_factory().begin() as database:
        run = database.get(MarketResearchRun, UUID(category_run_id))
        if run is None:
            return {"run_id": category_run_id, "status": "MISSING"}
        if run.state in {"COMPLETED", "BLOCKED"}:
            return {"run_id": category_run_id, "status": run.state}
        source_selection = _collect_category_sources(database, run.category)
        evaluated = execute_market_research(
            database,
            category=run.category,
            method_version=run.method_version,
            existing_run=run,
            source_selection=source_selection,
        )
        if evaluated.state == "COMPLETED":
            port = _analysis_port(database, evaluated)
            if port is None:
                evaluated.llm_analysis_state = "UNAVAILABLE"
            else:
                try:
                    run_advisory_analysis(
                        database,
                        evaluated,
                        port,
                        evidence=_advisory_evidence(database, evaluated),
                        now=utc_now(),
                    )
                finally:
                    _close_port(port)
        outcome = "BLOCKED" if evaluated.state == "BLOCKED" else "RECOMMENDED"
        record_category_outcome(
            database,
            evaluated,
            outcome=outcome,
            block_reasons=evaluated.block_reasons,
            completed_at=evaluated.completed_at or utc_now(),
        )
    return {"run_id": category_run_id, "status": outcome}


@shared_task(name="traderx.market_research.retry_llm", acks_late=True)
def retry_pinned_analysis(category_run_id: str) -> dict[str, str]:
    """Durable checkpoint for a user-requested same-pin retry.

    Runtime adapter construction remains catalogue-bound; unavailable credentials leave
    the advisory state visible without affecting the deterministic result.
    """

    with session_factory().begin() as database:
        run = database.get(MarketResearchRun, UUID(category_run_id))
        if run is None:
            return {"run_id": category_run_id, "status": "MISSING"}
        port = _analysis_port(database, run)
        if port is None:
            run.llm_analysis_state = "UNAVAILABLE"
            status = "UNAVAILABLE"
        else:
            try:
                attempt = retry_advisory_analysis(
                    database,
                    run,
                    port,
                    evidence=_advisory_evidence(database, run),
                    now=utc_now(),
                )
                status = attempt.state
            finally:
                _close_port(port)
    return {"run_id": category_run_id, "status": status, "authoritative": "false"}


_SPECIALISTS = {
    "COMMODITY": "CME_GROUP",
    "FOREX": "CBOE_FX_SPOT",
    "CRYPTO": "COINBASE_EXCHANGE",
}
_REQUIRED_CAPABILITIES = {
    "COMMODITY": (MarketDataCapability.TRADED_VOLUME, MarketDataCapability.OPEN_INTEREST),
    "FOREX": (MarketDataCapability.TRADED_VOLUME, MarketDataCapability.ORDER_BOOK),
    "CRYPTO": (MarketDataCapability.TRADED_VOLUME, MarketDataCapability.ORDER_BOOK),
}


def _collect_category_sources(database: Session, category: str) -> SourceSelection:
    """Collect mapped specialist evidence, then apply the governed fallback order."""

    now = utc_now()
    provider = _SPECIALISTS[category]
    integration = database.scalar(
        select(Integration).where(
            Integration.provider == provider,
            Integration.state == "HEALTHY",
        )
    )
    attempts: list[SourceAttempt] = []
    specialist: list[SourceEvidence] = []
    if integration is None:
        attempts.append(SourceAttempt(provider, 3, False, "QUALIFIED_INTEGRATION_UNAVAILABLE"))
    else:
        transport: ProviderHttpTransport | None = None
        try:
            adapter, transport = _market_data_adapter(database, integration)
            specialist = _collect_specialist_evidence(
                database,
                integration,
                adapter,
                category=category,
                evaluated_at=now,
                raw_hash=lambda: transport.last_response_hash if transport else None,
            )
            complete_liquidity = any(item.capability == "LIQUIDITY" for item in specialist)
            attempts.append(SourceAttempt(provider, 1, complete_liquidity, None))
            if not complete_liquidity:
                attempts.append(SourceAttempt(provider, 3, False, "MAPPING_OR_DATA_UNAVAILABLE"))
        except ProviderTransportError as error:
            attempts.append(SourceAttempt(provider, 3, False, error.kind))
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            attempts.append(SourceAttempt(provider, 3, False, "PROVIDER_COLLECTION_FAILED"))
        finally:
            if transport is not None:
                transport.close()
    mt5 = _mt5_fallback_evidence(database, category=category, evaluated_at=now)
    cached = _cached_external_evidence(database, category=category, evaluated_at=now)
    return select_market_source(
        specialist_attempts=attempts,
        specialist_evidence=specialist,
        mt5_evidence=mt5,
        cached_external_evidence=cached,
        required_capabilities={"LIQUIDITY"},
    )


def _market_data_adapter(database: Session, integration: Integration):  # type: ignore[no-untyped-def]
    credentials = _credentials(database, integration)
    token = str(credentials.get("api_token")) if credentials.get("api_token") else None
    transport = ProviderHttpTransport(integration.provider, credential=token)
    if integration.provider == "CME_GROUP":
        return CmeGroupAdapter(transport, entitlement_verified=True), transport
    if integration.provider == "CBOE_FX_SPOT":
        return CboeFxSpotAdapter(transport, entitlement_verified=True), transport
    if integration.provider == "COINBASE_EXCHANGE":
        return CoinbaseExchangeAdapter(transport), transport
    transport.close()
    raise ValueError("integration is not a category specialist")


def _collect_specialist_evidence(
    database: Session,
    integration: Integration,
    adapter,  # type: ignore[no-untyped-def]
    *,
    category: str,
    evaluated_at,
    raw_hash,  # type: ignore[no-untyped-def]
) -> list[SourceEvidence]:
    evidence: list[SourceEvidence] = []
    complete_by_instrument: dict[UUID, set[str]] = {}
    aliases = list(
        database.scalars(
            select(InstrumentAlias)
            .join(Instrument, Instrument.id == InstrumentAlias.instrument_id)
            .where(
                Instrument.category == category,
                InstrumentAlias.integration_id == integration.id,
                InstrumentAlias.approved_at.is_not(None),
                InstrumentAlias.valid_to.is_(None),
            )
        )
    )
    for alias in aliases:
        for capability in _REQUIRED_CAPABILITIES[category]:
            observations = adapter.get_observations(alias.native_symbol, capability)
            if not observations:
                continue
            _record_specialist_metric(
                database,
                alias,
                integration,
                capability,
                observations,
                raw_reference=raw_hash(),
            )
            latest = max(
                (item.observed_at for item in observations if item.observed_at is not None),
                default=None,
            )
            policy = _freshness_policy(database, integration.provider, capability.value)
            item = build_source_evidence(
                provider=integration.provider,
                capability=capability.value,
                semantics=SourceSemantics.ACTUAL,
                source_role=SourceRole.SPECIALIST_PRIMARY,
                observed_at=latest,
                received_at=max(item.received_at for item in observations),
                evaluated_at=evaluated_at,
                policy=policy,
                venue=alias.venue,
                provider_symbol=alias.native_symbol,
                canonical_instrument_id=str(alias.instrument_id),
                mapping_revision=alias.mapping_revision,
                entitlement_status=integration.entitlement_status,
                complete=all(item.complete for item in observations),
                quality="VERIFIED",
                conflict_state=ConflictState.CLEAR,
                raw_reference=raw_hash(),
            )
            evidence.append(item)
            if item.qualifies:
                complete_by_instrument.setdefault(alias.instrument_id, set()).add(capability.value)
    required = {item.value for item in _REQUIRED_CAPABILITIES[category]}
    for instrument_id, capabilities in complete_by_instrument.items():
        if not required <= capabilities:
            continue
        components = [
            item
            for item in evidence
            if item.canonical_instrument_id == str(instrument_id)
            and item.capability in required
        ]
        evidence.append(
            _composite_liquidity_evidence(
                components,
                role=SourceRole.SPECIALIST_PRIMARY,
                semantics=SourceSemantics.ACTUAL,
            )
        )
    return evidence


def _record_specialist_metric(
    database: Session,
    alias: InstrumentAlias,
    integration: Integration,
    capability: MarketDataCapability,
    observations,  # type: ignore[no-untyped-def]
    *,
    raw_reference: str | None,
) -> None:
    instrument = database.get(Instrument, alias.instrument_id)
    if instrument is None:
        return
    value = _observation_metric(observations, capability)
    if value is None or value <= 0:
        return
    existing = instrument.contract_spec.get("specialist_metrics", {})
    metrics = dict(existing) if isinstance(existing, dict) else {}
    metrics[capability.value] = str(value)
    metrics.update(
        {
            "provider": integration.provider,
            "venue": alias.venue,
            "mapping_revision": alias.mapping_revision,
            "catalogue_revision": integration.catalogue_revision,
            "raw_reference": raw_reference,
        }
    )
    instrument.contract_spec = {**instrument.contract_spec, "specialist_metrics": metrics}


def _observation_metric(observations, capability: MarketDataCapability):  # type: ignore[no-untyped-def]
    if capability == MarketDataCapability.ORDER_BOOK:
        total = Decimal("0")
        for observation in observations:
            for side in ("bids", "asks", "depth"):
                levels = observation.payload.get(side, [])
                if not isinstance(levels, list):
                    continue
                for level in levels:
                    if isinstance(level, (list, tuple)) and len(level) >= 2:
                        total += _decimal_or_zero(level[1])
                    elif isinstance(level, dict):
                        total += _decimal_or_zero(
                            level.get("size") or level.get("volume") or level.get("quantity")
                        )
        return total or None
    keys = (
        ("open_interest", "openInterest")
        if capability == MarketDataCapability.OPEN_INTEREST
        else ("traded_volume", "volume", "size", "quantity")
    )
    values = [
        _decimal_or_zero(observation.payload.get(key))
        for observation in observations
        for key in keys
        if observation.payload.get(key) is not None
    ]
    if not values:
        return None
    return max(values) if capability == MarketDataCapability.OPEN_INTEREST else sum(values)


def _decimal_or_zero(value) -> Decimal:  # type: ignore[no-untyped-def]
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _mt5_fallback_evidence(
    database: Session, *, category: str, evaluated_at
) -> list[SourceEvidence]:  # type: ignore[no-untyped-def]
    # Commodity and crypto liquidity require actual specialist measures in V1.
    if category != "FOREX":
        return []
    evidence: list[SourceEvidence] = []
    for instrument in database.scalars(
        select(Instrument).where(Instrument.category == category)
    ):
        spec = instrument.contract_spec
        if not spec.get("tick_volumes") or spec.get("bid") is None or spec.get("ask") is None:
            continue
        observed_at = _instant(spec.get("observed_at"))
        policy = _freshness_policy(database, "MT5_TERMINAL_BRIDGE", "CANDLES")
        evidence.append(
            build_source_evidence(
                provider="MT5_TERMINAL_BRIDGE",
                capability="LIQUIDITY",
                semantics=SourceSemantics.BROKER_PROXY,
                source_role=SourceRole.FALLBACK_MT5,
                observed_at=observed_at,
                received_at=evaluated_at,
                evaluated_at=evaluated_at,
                policy=policy,
                provider_symbol=instrument.symbol,
                canonical_instrument_id=str(instrument.id),
                mapping_revision="MT5_BROKER_AUTHORITY",
                entitlement_status="NOT_REQUIRED",
                complete=True,
                quality="VERIFIED",
                conflict_state=ConflictState.CLEAR,
                fallback_reason="SPECIALIST_RETRIES_EXHAUSTED",
            )
        )
    return evidence


def _cached_external_evidence(
    database: Session, *, category: str, evaluated_at
) -> list[SourceEvidence]:  # type: ignore[no-untyped-def]
    cached: list[SourceEvidence] = []
    for instrument in database.scalars(select(Instrument).where(Instrument.category == category)):
        values = instrument.contract_spec.get("cached_external_evidence", [])
        if not isinstance(values, list):
            continue
        for raw in values:
            if not isinstance(raw, dict) or raw.get("capability") != "LIQUIDITY":
                continue
            provider = str(raw.get("provider", ""))
            observed_at = _instant(raw.get("observed_at"))
            maximum_age = int(raw.get("maximum_age_seconds", 60))
            cached.append(
                build_source_evidence(
                    provider=provider,
                    capability="LIQUIDITY",
                    semantics=SourceSemantics(str(raw.get("semantics", "ACTUAL"))),
                    source_role=SourceRole.FALLBACK_CACHED_EXTERNAL,
                    observed_at=observed_at,
                    received_at=_instant(raw.get("received_at")) or evaluated_at,
                    evaluated_at=evaluated_at,
                    policy=FreshnessPolicy(
                        provider,
                        "LIQUIDITY",
                        str(raw.get("freshness_policy_version", "cached-v1")),
                        timedelta(seconds=maximum_age),
                    ),
                    venue=str(raw.get("venue")) if raw.get("venue") else None,
                    provider_symbol=str(raw.get("provider_symbol"))
                    if raw.get("provider_symbol")
                    else None,
                    canonical_instrument_id=str(instrument.id),
                    mapping_revision=str(raw.get("mapping_revision"))
                    if raw.get("mapping_revision")
                    else None,
                    entitlement_status=str(raw.get("entitlement_status", "UNVERIFIED")),
                    complete=bool(raw.get("complete")),
                    quality=str(raw.get("quality", "UNKNOWN")),
                    conflict_state=ConflictState(str(raw.get("conflict_state", "UNCHECKED"))),
                    fallback_reason="SPECIALIST_RETRIES_EXHAUSTED",
                    raw_reference=str(raw.get("raw_reference"))
                    if raw.get("raw_reference")
                    else None,
                )
            )
    return cached


def _composite_liquidity_evidence(
    components: list[SourceEvidence], *, role: SourceRole, semantics: SourceSemantics
) -> SourceEvidence:  # type: ignore[no-untyped-def]
    first = components[0]
    observed = min(
        (item.observed_at for item in components if item.observed_at is not None),
        default=None,
    )
    return SourceEvidence(
        provider=first.provider,
        capability="LIQUIDITY",
        semantics=semantics,
        source_role=role,
        freshness=FreshnessState.FRESH,
        freshness_policy_version="+".join(
            sorted({item.freshness_policy_version for item in components})
        ),
        observed_at=observed,
        received_at=max(item.received_at for item in components),
        age_seconds=max((item.age_seconds or 0 for item in components), default=0),
        venue=first.venue,
        provider_symbol=first.provider_symbol,
        canonical_instrument_id=first.canonical_instrument_id,
        mapping_revision=first.mapping_revision,
        entitlement_status=first.entitlement_status,
        complete=all(item.complete for item in components),
        quality="VERIFIED" if all(item.quality == "VERIFIED" for item in components) else "UNKNOWN",
        conflict_state=(
            ConflictState.CLEAR
            if all(item.conflict_state != ConflictState.MATERIAL_CONFLICT for item in components)
            else ConflictState.MATERIAL_CONFLICT
        ),
        raw_reference="+".join(item.raw_reference or "" for item in components),
    )


def _freshness_policy(
    database: Session, provider: str, capability: str
) -> FreshnessPolicy:
    row = database.scalar(
        select(FreshnessPolicyVersion)
        .where(
            FreshnessPolicyVersion.provider_key == provider,
            FreshnessPolicyVersion.capability == capability,
            FreshnessPolicyVersion.retired_at.is_(None),
        )
        .order_by(FreshnessPolicyVersion.effective_from.desc())
        .limit(1)
    )
    maximum_age = row.maximum_age_seconds if row else 60
    return FreshnessPolicy(
        provider,
        capability,
        row.policy_version if row else "freshness-default-v1",
        timedelta(seconds=maximum_age),
    )


def _analysis_port(database: Session, run: MarketResearchRun):  # type: ignore[no-untyped-def]
    if run.coordinated_run_id is None:
        return None
    parent = database.get(CoordinatedMarketResearchRun, run.coordinated_run_id)
    if parent is None or parent.llm_integration_id is None or parent.exact_model_id is None:
        return None
    integration = database.get(Integration, parent.llm_integration_id)
    if integration is None or integration.state != "HEALTHY" or integration.provider != parent.llm_provider_key:
        return None
    credentials = _credentials(database, integration)
    api_key = str(credentials.get("api_key", ""))
    client = httpx.Client(timeout=get_settings().llm_attempt_timeout_seconds)
    if integration.provider == "OPENAI_RESPONSES":
        return OpenAIResponsesAdapter(api_key, client=client)
    if integration.provider == "ANTHROPIC_MESSAGES":
        return AnthropicMessagesAdapter(api_key, client=client)
    client.close()
    return None


def _credentials(database: Session, integration: Integration) -> dict[str, object]:
    credential = database.scalar(
        select(CredentialVersion)
        .where(
            CredentialVersion.integration_id == integration.id,
            CredentialVersion.active.is_(True),
        )
        .order_by(CredentialVersion.created_at.desc())
        .limit(1)
    )
    if credential is None:
        return {}
    encrypted = EncryptedSecret(**json.loads(credential.encrypted_value))
    return SecretBox(
        get_settings().encryption_key_b64.get_secret_value(), key_version=credential.key_version
    ).decrypt(encrypted)


def _advisory_evidence(database: Session, run: MarketResearchRun) -> dict[str, object]:
    assessments = list(
        database.scalars(
            select(CandidateAssessment)
            .where(CandidateAssessment.research_run_id == run.id)
            .order_by(CandidateAssessment.rank, CandidateAssessment.id)
        )
    )
    return {
        "category": run.category,
        "methodology_version": run.method_version,
        "deterministic_result_hash": run.deterministic_result_hash,
        "source_manifest": run.source_manifest,
        "fallback_path": run.fallback_path,
        "candidates": [
            {
                "instrument_id": str(item.instrument_id),
                "eligible": item.eligible,
                "components": item.components,
                "score": str(item.score) if item.score is not None else None,
                "rank": item.rank,
                "reason_codes": item.gate_evidence.get("reason_codes", []),
            }
            for item in assessments
        ],
    }


def _close_port(port) -> None:  # type: ignore[no-untyped-def]
    client = getattr(port, "_client", None)
    if client is not None:
        client.close()


def _instant(value):  # type: ignore[no-untyped-def]
    if value is None:
        return None
    if hasattr(value, "tzinfo"):
        return value
    from datetime import datetime

    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _start_job(database: Session, background_job_id: str | None) -> BackgroundJob | None:
    if background_job_id is None:
        return None
    job = database.get(BackgroundJob, UUID(background_job_id))
    if job is None:
        raise InvalidTransition("the durable market job does not exist")
    if JobState(job.state or JobState.QUEUED) == JobState.QUEUED:
        job.transition(JobState.RUNNING)
        job.started_at = utc_now()
        job.attempt_count += 1
    if JobState(job.state) != JobState.RUNNING:
        raise InvalidTransition("the durable market job is not runnable")
    return job
