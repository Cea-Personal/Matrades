from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from celery import shared_task
from sqlalchemy import func, select

from traderx.integrations.broker_model import Mt5BridgeAgent
from traderx.integrations.model import Integration, IntegrationHealthObservation
from traderx.notifications.model import DeliveryAttempt, NotificationEvent, RoutedNotification
from traderx.notifications.providers import (
    DeliveryProvider,
    DeliveryUnavailable,
    UnconfiguredExternalProvider,
    WebInboxProvider,
)
from traderx.notifications.router import retryable, route_event
from traderx.shared.types import utc_now
from traderx.strategies.health import observe_live_strategy_health
from traderx_worker.tasks.database import session_factory


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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
