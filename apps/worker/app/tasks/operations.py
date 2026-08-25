from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from apps.worker.app.celery_app import celery_app
from modules.credentials.vault import EnvelopeCipher
from modules.notifications.providers import NotificationDeliveryError, send_notification
from packages.shared.config import settings
from packages.shared.database import unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore


@celery_app.task
def project_journal(event_id: str) -> dict:
    return {"event_id": event_id, "projected": True}


@celery_app.task
def rollup_performance(owner_id: str) -> dict:
    return {"owner_id": owner_id, "rolled_up": True}


@celery_app.task
def evaluate_strategy_health(version_id: str) -> dict:
    return {"version_id": version_id, "active_mutated": False}


async def _deliver_notification(notification_id: UUID) -> dict:
    async with unit_of_work() as session:
        notification = await session.get(ResourceRecord, notification_id)
        if notification is None or notification.kind != "notification":
            raise RuntimeError("notification not found")
        store = ResourceStore(session)
        preferences = await store.list("notification_preferences", notification.owner_id)
        preference = (
            preferences[0].data
            if preferences
            else {
                "in_app": True,
                "telegram": False,
                "pushover": False,
                "urgent_only_external": True,
            }
        )
        channels = await store.list("notification_channel", notification.owner_id)
        credentials = {
            str(item.id): item for item in await store.list("credential", notification.owner_id)
        }
        data = notification.data
        title = str(data.get("title") or data.get("event_type") or "Matrades notification")
        message = str(data.get("message") or data.get("body") or "")
        urgency = str(data.get("urgency") or data.get("priority") or "NORMAL").upper()
        receipts: list[dict] = []
        failures: list[dict] = []
        for channel in channels:
            if channel.state != "ACTIVE" or not channel.data.get("enabled", True):
                continue
            provider = str(channel.data.get("provider", "")).upper()
            if not preference.get(provider.lower(), False):
                continue
            if preference.get("urgent_only_external", True) and urgency not in {
                "URGENT",
                "CRITICAL",
                "HIGH",
            }:
                continue
            credential = credentials.get(str(channel.data.get("credential_id")))
            try:
                if credential is None:
                    raise NotificationDeliveryError("notification credential unavailable")
                secret = EnvelopeCipher(settings.secret_key.get_secret_value().encode()).decrypt(
                    notification.owner_id, credential.data["envelope"]
                )
                receipts.append(
                    await send_notification(
                        provider,
                        secret,
                        str(channel.data.get("destination", "")),
                        title=title,
                        message=message,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - one bad channel must not block inbox delivery
                failures.append(
                    {"channel_id": str(channel.id), "provider": provider, "error": str(exc)[:180]}
                )
        state = "DEGRADED" if failures else "DELIVERED"
        updated = await store.update(
            notification,
            {
                **data,
                "delivery_state": state,
                "delivered_at": datetime.now(UTC).isoformat()
                if not failures
                else data.get("delivered_at"),
                "delivery_receipts": receipts,
                "delivery_failures": failures,
            },
            state=state,
            event_type="notification.delivery_completed"
            if not failures
            else "notification.delivery_degraded",
        )
        return {
            "notification_id": str(updated.id),
            "state": state,
            "receipts": receipts,
            "failures": failures,
        }


@celery_app.task(name="apps.worker.app.tasks.operations.deliver_notification")
def deliver_notification(notification_id: str) -> dict:
    return asyncio.run(_deliver_notification(UUID(notification_id)))
