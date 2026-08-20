from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

import httpx
from celery import shared_task
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from traderx.integrations.crypto import EncryptedSecret, SecretBox
from traderx.integrations.model import CredentialVersion, FreshnessPolicyVersion, Integration
from traderx.integrations.ports import (
    LlmAnalysisPort,
    MarketDataCapability,
    MarketDataPort,
    ProviderObservation,
    SourceSemantics,
)
from traderx.integrations.providers.anthropic_messages import AnthropicMessagesAdapter
from traderx.integrations.providers.litellm_proxy import LiteLlmProxyAdapter
from traderx.integrations.providers.openai_responses import OpenAIResponsesAdapter
from traderx.jobs.model import BackgroundJob, JobState
from traderx.market_data.ingestion import ProviderBatch, persist_provider_observations
from traderx.market_data.model import (
    DataSetManifest,
    Instrument,
    InstrumentAlias,
    MarketObservation,
)
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
from traderx.market_research.coordinator import claim_category_run, record_category_outcome
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
from traderx.notifications.router import notify_market_research_owners
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
        parent = database.scalar(
            select(CoordinatedMarketResearchRun)
            .where(CoordinatedMarketResearchRun.id == UUID(coordinated_run_id))
            .with_for_update(skip_locked=True)
        )
        if parent is None:
            return {"run_id": coordinated_run_id, "status": "NOT_CLAIMED"}
        if parent.state in {"COMPLETED", "PARTIAL", "FAILED"}:
            return {"run_id": coordinated_run_id, "status": parent.state}
        now = utc_now()
        parent.state = "RUNNING"
        parent.started_at = parent.started_at or now
        children = list(
            database.scalars(
                select(MarketResearchRun)
                .where(
                    MarketResearchRun.coordinated_run_id == parent.id,
                    or_(
                        MarketResearchRun.state == "QUEUED",
                        and_(
                            MarketResearchRun.state == "RUNNING",
                            or_(
                                MarketResearchRun.lease_expires_at.is_(None),
                                MarketResearchRun.lease_expires_at <= now,
                            ),
                        ),
                    ),
                )
                .order_by(MarketResearchRun.category)
            )
        )
        child_ids = [str(child.id) for child in children]
    for child_id in child_ids:
        run_coordinated_category.delay(child_id)
    return {"run_id": coordinated_run_id, "status": "DISPATCHED", "children": child_ids}


@shared_task(name="traderx.market_research.run_category", bind=True, acks_late=True)
def run_coordinated_category(self: object, category_run_id: str) -> dict[str, str]:
    """Idempotently evaluate one child; ranking never changes an active assignment."""

    run_id = UUID(category_run_id)
    lease_token = _task_id(self)
    with session_factory().begin() as database:
        claim = claim_category_run(
            database,
            run_id,
            now=utc_now(),
            lease_owner="celery-market-research",
            lease_token=lease_token,
        )
    if claim is None:
        return {"run_id": category_run_id, "status": "NOT_CLAIMED"}

    try:
        with session_factory().begin() as database:
            run = database.scalar(
                select(MarketResearchRun)
                .where(
                    MarketResearchRun.id == run_id,
                    MarketResearchRun.lease_token == lease_token,
                )
                .with_for_update()
            )
            if run is None:
                return {"run_id": category_run_id, "status": "FENCED"}
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
                    notify_market_research_owners(
                        database,
                        kind="LLM_UNAVAILABLE",
                        subject_id=str(evaluated.id),
                        payload={
                            "category": evaluated.category,
                            "failure_reason": "PINNED_MODEL_INTEGRATION_UNAVAILABLE",
                            "retry_eligible": True,
                            "authoritative": False,
                        },
                        created_at=utc_now(),
                    )
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
    except Exception as error:
        reason = f"WORKER_{type(error).__name__.upper()}"
        with session_factory().begin() as database:
            run = database.scalar(
                select(MarketResearchRun)
                .where(
                    MarketResearchRun.id == run_id,
                    MarketResearchRun.lease_token == lease_token,
                )
                .with_for_update()
            )
            if run is None:
                return {"run_id": category_run_id, "status": "FENCED"}
            run.current_error = reason
            if run.attempt_count >= 3:
                record_category_outcome(
                    database,
                    run,
                    outcome="FAILED",
                    block_reasons=[reason],
                    completed_at=utc_now(),
                )
                status = "FAILED"
            else:
                run.state = "QUEUED"
                run.lease_owner = None
                run.lease_token = None
                run.lease_expires_at = None
                status = "RETRY_QUEUED"
        return {"run_id": category_run_id, "status": status}


@shared_task(name="traderx.market_research.retry_llm", bind=True, acks_late=True)
def retry_pinned_analysis(self: object, category_run_id: str) -> dict[str, str]:
    """Durable checkpoint for a user-requested same-pin retry.

    Runtime adapter construction remains catalogue-bound; unavailable credentials leave
    the advisory state visible without affecting the deterministic result.
    """

    run_id = UUID(category_run_id)
    lease_token = _task_id(self)
    now = utc_now()
    with session_factory().begin() as database:
        run = database.scalar(
            select(MarketResearchRun)
            .where(MarketResearchRun.id == run_id)
            .with_for_update(skip_locked=True)
        )
        if run is None:
            return {"run_id": category_run_id, "status": "NOT_CLAIMED"}
        if run.llm_analysis_state == "RUNNING" and (
            run.lease_expires_at is None or run.lease_expires_at > now
        ):
            return {"run_id": category_run_id, "status": "NOT_CLAIMED"}
        if run.llm_analysis_state not in {"RETRY_QUEUED", "RUNNING"}:
            return {"run_id": category_run_id, "status": run.llm_analysis_state}
        run.llm_analysis_state = "RUNNING"
        run.lease_owner = "celery-market-research-llm"
        run.lease_token = lease_token
        run.lease_expires_at = now + timedelta(minutes=15)
    with session_factory().begin() as database:
        run = database.scalar(
            select(MarketResearchRun)
            .where(
                MarketResearchRun.id == run_id,
                MarketResearchRun.lease_token == lease_token,
            )
            .with_for_update()
        )
        if run is None:
            return {"run_id": category_run_id, "status": "FENCED"}
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
        run.lease_owner = None
        run.lease_token = None
        run.lease_expires_at = None
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
_COLLECT_CAPABILITIES = {
    **_REQUIRED_CAPABILITIES,
    "COMMODITY": (
        MarketDataCapability.TRADED_VOLUME,
        MarketDataCapability.OPEN_INTEREST,
        MarketDataCapability.ORDER_BOOK,
    ),
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
            for conflict in (
                item
                for item in specialist
                if item.conflict_state == ConflictState.MATERIAL_CONFLICT
            ):
                notify_market_research_owners(
                    database,
                    kind="SOURCE_CONFLICT",
                    subject_id=conflict.raw_reference or f"{provider}:{category}",
                    payload={
                        "category": category,
                        "provider": provider,
                        "capability": conflict.capability,
                        "provider_symbol": conflict.provider_symbol,
                        "active_assignment_changed": False,
                    },
                    created_at=now,
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


def _market_data_adapter(
    database: Session, integration: Integration
) -> tuple[MarketDataPort, ProviderHttpTransport]:
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
    adapter: MarketDataPort,
    *,
    category: str,
    evaluated_at: datetime,
    raw_hash: Callable[[], str | None],
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
        for capability in _COLLECT_CAPABILITIES[category]:
            observations = adapter.get_observations(alias.native_symbol, capability)
            policy = _freshness_policy(database, integration.provider, capability.value)
            value = _observation_metric(observations, capability)
            coherent = bool(observations) and _observations_are_coherent(observations)
            complete = bool(observations) and value is not None and value > 0 and coherent
            conflict = (
                ConflictState.CLEAR
                if coherent
                else ConflictState.MATERIAL_CONFLICT
                if observations
                else ConflictState.UNCHECKED
            )
            retained = persist_provider_observations(
                database,
                instrument_id=alias.instrument_id,
                integration_id=integration.id,
                batch=ProviderBatch(
                    provider=integration.provider,
                    provider_symbol=alias.native_symbol,
                    retrieved_at=evaluated_at,
                    payload=json.dumps(
                        [item.payload for item in observations],
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ).encode(),
                    venue=alias.venue,
                    capability=capability.value,
                    semantics=SourceSemantics.ACTUAL.value,
                    source_role=SourceRole.SPECIALIST_PRIMARY.value,
                    catalogue_revision=integration.catalogue_revision,
                    adapter_revision=integration.adapter_revision,
                    mapping_revision=alias.mapping_revision,
                    freshness_policy_version=policy.version,
                    retry_policy_version="retry-2026-08-v1",
                    entitlement_status=integration.entitlement_status,
                    source_observed_at=max(
                        (item.observed_at for item in observations if item.observed_at is not None),
                        default=None,
                    ),
                    raw_reference=raw_hash(),
                ),
                observations=observations,
                normalized_value=value,
                quality="VERIFIED" if complete else "QUARANTINED",
                conflict_state=conflict,
                complete=complete,
            )
            latest = max(
                (item.observed_at for item in observations if item.observed_at is not None),
                default=None,
            )
            item = build_source_evidence(
                provider=integration.provider,
                capability=capability.value,
                semantics=(SourceSemantics.ACTUAL if complete else SourceSemantics.UNAVAILABLE),
                source_role=SourceRole.SPECIALIST_PRIMARY,
                observed_at=latest,
                received_at=max((item.received_at for item in observations), default=evaluated_at),
                evaluated_at=evaluated_at,
                policy=policy,
                venue=alias.venue,
                provider_symbol=alias.native_symbol,
                canonical_instrument_id=str(alias.instrument_id),
                mapping_revision=alias.mapping_revision,
                entitlement_status=integration.entitlement_status,
                complete=complete,
                quality="VERIFIED" if complete else "QUARANTINED",
                conflict_state=conflict,
                raw_reference=(
                    f"dataset-manifest:{retained.manifest.id}:{retained.manifest.content_hash}"
                ),
                measures={"value": str(value)} if value is not None else {},
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
            if item.canonical_instrument_id == str(instrument_id) and item.capability in required
        ]
        evidence.append(
            _composite_liquidity_evidence(
                components,
                role=SourceRole.SPECIALIST_PRIMARY,
                semantics=SourceSemantics.ACTUAL,
            )
        )
    return evidence


def _observation_metric(
    observations: Sequence[ProviderObservation], capability: MarketDataCapability
) -> Decimal | None:
    if not observations:
        return None
    if capability == MarketDataCapability.ORDER_BOOK:
        total = Decimal("0")
        for observation in observations:
            found_side = False
            for side in ("bids", "asks", "depth"):
                levels = observation.payload.get(side, [])
                if not isinstance(levels, list):
                    return None
                if levels:
                    found_side = True
                for level in levels:
                    if isinstance(level, (list, tuple)) and len(level) >= 2:
                        value = _strict_decimal(level[1])
                    elif isinstance(level, dict):
                        value = _strict_decimal(
                            level.get("size") or level.get("volume") or level.get("quantity")
                        )
                    else:
                        return None
                    if value is None or value <= 0:
                        return None
                    total += value
            if not found_side:
                return None
        return total if total > 0 else None
    keys = (
        ("open_interest", "openInterest")
        if capability == MarketDataCapability.OPEN_INTEREST
        else ("traded_volume", "volume", "size", "quantity")
    )
    values: list[Decimal] = []
    for observation in observations:
        raw = next(
            (
                observation.payload.get(key)
                for key in keys
                if observation.payload.get(key) is not None
            ),
            None,
        )
        value = _strict_decimal(raw)
        if value is None or value <= 0:
            return None
        values.append(value)
    if not values:
        return None
    return (
        max(values)
        if capability == MarketDataCapability.OPEN_INTEREST
        else sum(values, Decimal("0"))
    )


def _strict_decimal(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _observations_are_coherent(observations: Sequence[ProviderObservation]) -> bool:
    """Reject contradictory duplicate provider identities instead of averaging them."""

    seen: dict[tuple[str, str, str, str], str] = {}
    for item in observations:
        identity = (
            item.provider_event_id or "",
            item.sequence or "",
            item.revision or "",
            item.observed_at.isoformat() if item.observed_at else "",
        )
        payload_hash = json.dumps(item.payload, sort_keys=True, separators=(",", ":"), default=str)
        previous = seen.get(identity)
        if previous is not None and previous != payload_hash:
            return False
        seen[identity] = payload_hash
    return all(item.complete and item.observed_at is not None for item in observations)


def _mt5_fallback_evidence(
    database: Session, *, category: str, evaluated_at: datetime
) -> list[SourceEvidence]:
    # Commodity and crypto liquidity require actual specialist measures in V1.
    if category != "FOREX":
        return []
    evidence: list[SourceEvidence] = []
    for instrument in database.scalars(select(Instrument).where(Instrument.category == category)):
        spec = instrument.contract_spec
        if not spec.get("tick_volumes") or spec.get("bid") is None or spec.get("ask") is None:
            continue
        tick_volumes = _strict_decimal_values(spec.get("tick_volumes"))
        if not tick_volumes or any(value <= 0 for value in tick_volumes):
            continue
        broker_activity = sum(tick_volumes, Decimal("0"))
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
                measures={
                    "TRADED_VOLUME": str(broker_activity),
                    "ORDER_BOOK": str(broker_activity / Decimal(len(tick_volumes))),
                },
            )
        )
    return evidence


def _cached_external_evidence(
    database: Session, *, category: str, evaluated_at: datetime
) -> list[SourceEvidence]:
    cached: list[SourceEvidence] = []
    for instrument in database.scalars(select(Instrument).where(Instrument.category == category)):
        rows = database.execute(
            select(DataSetManifest, MarketObservation)
            .join(MarketObservation, MarketObservation.dataset_manifest_id == DataSetManifest.id)
            .where(
                MarketObservation.instrument_id == instrument.id,
                DataSetManifest.provider == _SPECIALISTS[category],
                DataSetManifest.source_role == SourceRole.SPECIALIST_PRIMARY.value,
            )
            .order_by(DataSetManifest.created_at.desc(), MarketObservation.observed_at.desc())
        ).all()
        latest_by_capability: dict[str, tuple[DataSetManifest, MarketObservation]] = {}
        for manifest, observation in rows:
            latest_by_capability.setdefault(manifest.capability, (manifest, observation))
        components: list[SourceEvidence] = []
        for capability in _REQUIRED_CAPABILITIES[category]:
            pair = latest_by_capability.get(capability.value)
            if pair is None:
                continue
            manifest, observation = pair
            policy = _freshness_policy(database, manifest.provider, manifest.capability)
            value = observation.measures.get("normalized_value")
            item = build_source_evidence(
                provider=manifest.provider,
                capability=manifest.capability,
                semantics=SourceSemantics(manifest.semantics),
                source_role=SourceRole.FALLBACK_CACHED_EXTERNAL,
                observed_at=manifest.source_observed_at,
                received_at=manifest.received_at or manifest.created_at,
                evaluated_at=evaluated_at,
                policy=policy,
                venue=manifest.venue,
                provider_symbol=manifest.provider_symbol,
                canonical_instrument_id=str(instrument.id),
                mapping_revision=manifest.mapping_revision,
                entitlement_status=manifest.entitlement_status,
                complete=manifest.complete,
                quality=manifest.quality,
                conflict_state=ConflictState(manifest.conflict_state),
                fallback_reason="SPECIALIST_RETRIES_EXHAUSTED",
                raw_reference=f"dataset-manifest:{manifest.id}:{manifest.content_hash}",
                measures={"value": str(value)} if value is not None else {},
            )
            components.append(item)
            cached.append(item)
        required = {item.value for item in _REQUIRED_CAPABILITIES[category]}
        qualified = {item.capability for item in components if item.qualifies}
        if required <= qualified:
            cached.append(
                _composite_liquidity_evidence(
                    components,
                    role=SourceRole.FALLBACK_CACHED_EXTERNAL,
                    semantics=SourceSemantics.ACTUAL,
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
        measures={
            item.capability: item.measures["value"]
            for item in components
            if item.measures.get("value") is not None
        },
    )


def _freshness_policy(database: Session, provider: str, capability: str) -> FreshnessPolicy:
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


def _analysis_port(database: Session, run: MarketResearchRun) -> LlmAnalysisPort | None:
    if run.coordinated_run_id is None:
        return None
    parent = database.get(CoordinatedMarketResearchRun, run.coordinated_run_id)
    if parent is None or parent.llm_integration_id is None or parent.exact_model_id is None:
        return None
    integration = database.get(Integration, parent.llm_integration_id)
    if (
        integration is None
        or integration.state != "HEALTHY"
        or integration.provider != parent.llm_provider_key
    ):
        return None
    credentials = _credentials(database, integration)
    credential_field = "virtual_key" if integration.provider == "LITELLM_PROXY" else "api_key"
    api_key = str(credentials.get(credential_field, ""))
    if not api_key:
        return None
    client = httpx.Client(timeout=get_settings().llm_attempt_timeout_seconds)
    if integration.provider == "OPENAI_RESPONSES":
        return OpenAIResponsesAdapter(api_key, client=client)
    if integration.provider == "ANTHROPIC_MESSAGES":
        return AnthropicMessagesAdapter(api_key, client=client)
    if integration.provider == "LITELLM_PROXY":
        return LiteLlmProxyAdapter(
            api_key,
            base_url=str(integration.configuration["base_url"]),
            client=client,
        )
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


def _close_port(port: LlmAnalysisPort) -> None:
    client = getattr(port, "_client", None)
    if client is not None:
        client.close()


def _instant(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _strict_decimal_values(value: object) -> list[Decimal] | None:
    if not isinstance(value, list):
        return None
    parsed = [_strict_decimal(item) for item in value]
    if any(item is None for item in parsed):
        return None
    return [item for item in parsed if item is not None]


def _task_id(task: object) -> str:
    request = getattr(task, "request", None)
    value = getattr(request, "id", None)
    return str(value) if value else str(uuid4())


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
