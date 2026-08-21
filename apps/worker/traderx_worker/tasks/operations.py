from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from celery import shared_task
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from traderx.integrations.broker_model import Mt5BridgeAgent
from traderx.integrations.crypto import EncryptedSecret, SecretBox
from traderx.integrations.model import CredentialVersion, Integration, IntegrationHealthObservation
from traderx.integrations.providers.anthropic_messages import AnthropicMessagesAdapter
from traderx.integrations.providers.litellm_proxy import LiteLlmProxyAdapter
from traderx.integrations.providers.openai_responses import OpenAIResponsesAdapter
from traderx.integrations.registry import approved_provider
from traderx.jobs.model import BackgroundJob, JobState
from traderx.market_data.providers.cboe_fx_spot import CboeFxSpotAdapter
from traderx.market_data.providers.cme_group import CmeGroupAdapter
from traderx.market_data.providers.coinbase_exchange import CoinbaseExchangeAdapter
from traderx.market_data.providers.http import ProviderHttpTransport, ProviderTransportError
from traderx.market_data.providers.twelve_data import TwelveDataAdapter
from traderx.notifications.model import DeliveryAttempt, NotificationEvent, RoutedNotification
from traderx.notifications.providers import (
    DeliveryProvider,
    DeliveryUnavailable,
    UnconfiguredExternalProvider,
    WebInboxProvider,
)
from traderx.notifications.router import notify_market_research_owners, retryable, route_event
from traderx.shared.config import get_settings
from traderx.shared.types import utc_now
from traderx.strategies.health import observe_live_strategy_health
from traderx_worker.tasks.database import session_factory


# Twelve Data's free tier has a daily credit budget. Its live health probe uses
# one `/price` request, so avoid consuming a credit each time the general
# operational-health task runs (once a minute).
TWELVE_DATA_HEALTH_INTERVAL = timedelta(minutes=15)


@shared_task(name="traderx.operations.notifications", bind=True, acks_late=True)
def deliver_notifications(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    delivered = 0
    failed = 0
    with session_factory().begin() as database:
        for event in database.scalars(select(NotificationEvent)):
            raw_user_id = event.payload.get("user_id")
            if raw_user_id is None:
                continue
            try:
                user_id = UUID(str(raw_user_id))
            except ValueError:
                continue
            route_event(database, event, user_id)
        pending = database.scalars(
            select(RoutedNotification).where(RoutedNotification.state == "PENDING")
        ).all()
        for routed in pending:
            notification_event = database.get(NotificationEvent, routed.event_id)
            if notification_event is None:
                routed.state = "FAILED"
                failed += 1
                continue
            attempt = (
                database.scalar(
                    select(func.max(DeliveryAttempt.attempt)).where(
                        DeliveryAttempt.routed_notification_id == routed.id
                    )
                )
                or 0
            ) + 1
            provider: DeliveryProvider = (
                WebInboxProvider()
                if routed.channel == "WEB"
                else UnconfiguredExternalProvider(routed.channel)
            )
            try:
                receipt = provider.deliver(
                    str(routed.id), json.dumps(notification_event.payload, sort_keys=True)
                )
                routed.state = "DELIVERED"
                database.add(
                    DeliveryAttempt(
                        routed_notification_id=routed.id,
                        attempt=attempt,
                        state="DELIVERED",
                        error=None,
                        attempted_at=utc_now(),
                    )
                )
                notification_event.payload = {
                    **notification_event.payload,
                    "provider_reference": receipt.provider_reference,
                }
                delivered += 1
            except DeliveryUnavailable as exc:
                will_retry = retryable(attempt)
                routed.state = "PENDING" if will_retry else "FAILED"
                database.add(
                    DeliveryAttempt(
                        routed_notification_id=routed.id,
                        attempt=attempt,
                        state="RETRY_PENDING" if will_retry else "FAILED",
                        error=str(exc),
                        attempted_at=utc_now(),
                    )
                )
                if not will_retry:
                    failed += 1
    return {"status": "COMPLETED", "delivered": str(delivered), "failed": str(failed)}


@shared_task(name="traderx.operations.health", bind=True, acks_late=True)
def poll_health(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    observed = 0
    with session_factory().begin() as database:
        now = utc_now()
        for integration in database.scalars(
            select(Integration).where(Integration.state != "REMOVED")
        ):
            if integration.provider != "MT5_TERMINAL_BRIDGE":
                latest = database.scalar(
                    select(IntegrationHealthObservation)
                    .where(IntegrationHealthObservation.integration_id == integration.id)
                    .order_by(IntegrationHealthObservation.observed_at.desc())
                    .limit(1)
                )
                if (
                    integration.provider == "TWELVE_DATA"
                    and latest is not None
                    and latest.observed_at >= now - TWELVE_DATA_HEALTH_INTERVAL
                ):
                    # Keep the last verified observation until its dedicated
                    # cadence is due. Other integrations retain their
                    # one-minute operational-health checks.
                    continue
                if integration.state == "DISABLED":
                    status = "DISABLED"
                    reason = None
                    latency_ms = None
                else:
                    status, reason, latency_ms = _live_probe_status(database, integration)
                    integration.state = status
                affected = tuple(integration.capabilities) if status != "HEALTHY" else ()
                database.add(
                    IntegrationHealthObservation(
                        integration_id=integration.id,
                        status=status,
                        evidence={
                            "provider": integration.provider,
                            "category": integration.category,
                            "integration_state": integration.state,
                            "entitlement_status": integration.entitlement_status,
                            "catalogue_revision": integration.catalogue_revision,
                            "credential_redacted": True,
                        },
                        observed_at=now,
                        last_success_at=(
                            now
                            if status == "HEALTHY"
                            else latest.last_success_at
                            if latest
                            else None
                        ),
                        latency_ms=latency_ms,
                        affected_capabilities=list(affected),
                        current_error=reason,
                    )
                )
                if reason and (latest is None or latest.current_error != reason):
                    kind = (
                        "ENTITLEMENT_LOST"
                        if approved_provider(integration.provider).entitlement_required
                        and reason in {"ENTITLEMENT_EVIDENCE_REQUIRED", "PROVIDER_AUTHORIZATION"}
                        else "SOURCE_STALE"
                    )
                    notify_market_research_owners(
                        database,
                        kind=kind,
                        subject_id=f"{integration.id}:{integration.version}:{reason}",
                        payload={
                            "integration_id": str(integration.id),
                            "provider": integration.provider,
                            "current_error": reason,
                            "affected_capabilities": list(affected),
                        },
                        created_at=now,
                    )
                observed += 1
                continue
            bridge = database.scalar(
                select(Mt5BridgeAgent).where(Mt5BridgeAgent.integration_id == integration.id)
            )
            fresh = bool(
                bridge
                and bridge.last_seen_at
                and (now - _aware(bridge.last_seen_at)).total_seconds() <= 60
            )
            status = "HEALTHY" if integration.state == "HEALTHY" and fresh else "DEGRADED"
            database.add(
                IntegrationHealthObservation(
                    integration_id=integration.id,
                    status=status,
                    evidence={
                        "provider": integration.provider,
                        "integration_state": integration.state,
                        "bridge_seen_within_seconds": 60,
                        "credential_redacted": True,
                    },
                    observed_at=now,
                )
            )
            observed += 1
        strategies = observe_live_strategy_health(database, observed_at=now)
    return {
        "status": "COMPLETED",
        "integrations_observed": str(observed),
        "strategies_observed": str(len(strategies)),
    }


@shared_task(name="traderx.operations.qualify_provider", bind=True, acks_late=True)
def qualify_provider(self, integration_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Probe one reviewed provider and retain only redacted qualification evidence."""

    with session_factory().begin() as database:
        integration = database.get(Integration, UUID(integration_id))
        if integration is None or integration.state == "REMOVED":
            return {"integration_id": integration_id, "status": "MISSING"}
        status, _reason = _qualify(database, integration, now=utc_now())
    return {"integration_id": integration_id, "status": status}


@shared_task(name="traderx.operations.run_queued_qualifications", bind=True, acks_late=True)
def run_queued_qualifications(self) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Claim durable UI-created qualification jobs without relying on the API process."""

    completed: list[str] = []
    with session_factory().begin() as database:
        jobs = list(
            database.scalars(
                select(BackgroundJob)
                .where(
                    BackgroundJob.job_type == "PROVIDER_QUALIFICATION",
                    BackgroundJob.state == JobState.QUEUED,
                )
                .order_by(BackgroundJob.created_at)
                .limit(10)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            job.transition(JobState.RUNNING)
            job.started_at = utc_now()
            job.attempt_count += 1
            raw_id = job.context.get("integration_id")
            try:
                integration = database.get(Integration, UUID(str(raw_id)))
            except (TypeError, ValueError):
                integration = None
            if integration is None or integration.state == "REMOVED":
                job.transition(JobState.FAILED)
                job.error_code = "INTEGRATION_NOT_AVAILABLE"
                job.finished_at = utc_now()
                continue
            status, reason = _qualify(database, integration, now=utc_now())
            job.progress = {"stage": "COMPLETED", "qualification_status": status}
            job.error_code = reason
            job.result_ref = "/api/v1/integrations/non-broker"
            job.transition(JobState.COMPLETED)
            job.finished_at = utc_now()
            completed.append(str(job.id))
    return {"status": "COMPLETED", "jobs": completed}


def _qualify(
    database: Session, integration: Integration, *, now: datetime
) -> tuple[str, str | None]:
    definition = approved_provider(integration.provider)
    status, reason, latency_ms = _live_probe_status(database, integration)
    integration.state = status
    if status == "HEALTHY" and definition.entitlement_required:
        integration.entitlement_status = "VERIFIED"
    database.add(
        IntegrationHealthObservation(
            integration_id=integration.id,
            status=status,
            evidence={
                "provider": integration.provider,
                "category": integration.category,
                "integration_state": status,
                "entitlement_status": integration.entitlement_status,
                "catalogue_revision": integration.catalogue_revision,
                "adapter_revision": integration.adapter_revision,
                "credential_redacted": True,
                "probe": "LIVE_REVIEWED_ENDPOINT",
                "capabilities": sorted(integration.capabilities),
            },
            observed_at=now,
            last_success_at=now if status == "HEALTHY" else None,
            latency_ms=latency_ms,
            current_error=reason,
            affected_capabilities=list(integration.capabilities) if reason else [],
        )
    )
    return status, reason


def _live_probe_status(
    database: Session, integration: Integration
) -> tuple[str, str | None, int | None]:
    """Probe a reviewed provider; never infer freshness from an older observation."""

    definition = approved_provider(integration.provider)
    credential = database.scalar(
        select(CredentialVersion)
        .where(
            CredentialVersion.integration_id == integration.id,
            CredentialVersion.active.is_(True),
        )
        .order_by(CredentialVersion.created_at.desc())
        .limit(1)
    )
    if definition.credential_required and credential is None:
        return "DEGRADED", "CREDENTIAL_REQUIRED", None
    if definition.entitlement_required and integration.entitlement_status not in {
        "DECLARED",
        "VERIFIED",
    }:
        return "DEGRADED", "ENTITLEMENT_EVIDENCE_REQUIRED", None

    started = time.perf_counter()
    try:
        credentials = _decrypt_credential(integration, credential)
        _probe(integration, credentials)
    except ProviderTransportError as error:
        reason = f"PROVIDER_{error.kind}"
        status = (
            "FAILED"
            if error.kind in {"AUTHENTICATION", "AUTHORIZATION", "PERMANENT_INPUT"}
            else "DEGRADED"
        )
        return status, reason, int((time.perf_counter() - started) * 1000)
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return (
            "DEGRADED",
            "PROVIDER_QUALIFICATION_FAILED",
            int((time.perf_counter() - started) * 1000),
        )
    return "HEALTHY", None, int((time.perf_counter() - started) * 1000)


def _decrypt_credential(
    integration: Integration, credential: CredentialVersion | None
) -> dict[str, object]:
    if credential is None:
        return {}
    encrypted = EncryptedSecret(**json.loads(credential.encrypted_value))
    return SecretBox(
        get_settings().encryption_key_b64.get_secret_value(), key_version=credential.key_version
    ).decrypt(encrypted)


def _probe(integration: Integration, credentials: dict[str, object]) -> None:
    definition = approved_provider(integration.provider)
    token = None
    if definition.credential_fields:
        token = str(credentials[next(iter(sorted(definition.credential_fields)))])
    if integration.provider in {"CME_GROUP", "CBOE_FX_SPOT", "COINBASE_EXCHANGE", "TWELVE_DATA"}:
        transport = ProviderHttpTransport(integration.provider, credential=token)
        try:
            if integration.provider == "CME_GROUP":
                result = CmeGroupAdapter(transport, entitlement_verified=True).test_connection()
            elif integration.provider == "CBOE_FX_SPOT":
                result = CboeFxSpotAdapter(transport, entitlement_verified=True).test_connection()
            elif integration.provider == "TWELVE_DATA":
                result = TwelveDataAdapter(transport).test_connection()
            else:
                result = CoinbaseExchangeAdapter(transport).test_connection()
        finally:
            transport.close()
    elif integration.provider in {"OPENAI_RESPONSES", "ANTHROPIC_MESSAGES", "LITELLM_PROXY"}:
        assert token is not None
        with httpx.Client(timeout=get_settings().provider_read_timeout_seconds) as client:
            if integration.provider == "OPENAI_RESPONSES":
                result = OpenAIResponsesAdapter(token, client=client).test_connection()
            elif integration.provider == "ANTHROPIC_MESSAGES":
                result = AnthropicMessagesAdapter(token, client=client).test_connection()
            else:
                result = LiteLlmProxyAdapter(
                    token,
                    base_url=str(integration.configuration["base_url"]),
                    client=client,
                ).test_connection()
    elif integration.provider in {"BLS", "BEA"}:
        # Health is limited to the documented machine-readable schedule endpoint;
        # no page scraping is permitted.
        url = (
            "https://www.bls.gov/schedule/news_release/bls.ics"
            if integration.provider == "BLS"
            else "https://www.bea.gov/news/schedule/icalendar"
        )
        with httpx.Client(timeout=get_settings().provider_read_timeout_seconds, follow_redirects=False) as client:
            response = client.get(url, headers={"Accept": "text/calendar"})
            response.raise_for_status()
        result = {"healthy": bool(response.content)}
    else:
        raise ValueError("provider does not expose a reviewed qualification probe")
    if not bool(result.get("healthy")):
        raise ValueError("provider qualification did not report healthy")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
