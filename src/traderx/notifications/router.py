from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.notifications.model import (
    NotificationEvent,
    NotificationPreference,
    RoutedNotification,
)


@dataclass(frozen=True, slots=True)
class DeliveryPlan:
    channels: tuple[str, ...]
    persist_web_inbox: bool


def route(*, severity: str, enabled_channels: set[str]) -> DeliveryPlan:
    channels = tuple(sorted(enabled_channels))
    return DeliveryPlan(channels, severity in {"CRITICAL", "HIGH"})


def retryable(attempt: int, maximum: int = 3) -> bool:
    return attempt < maximum


_SEVERITY = {"INFO": 0, "ACTION": 1, "WARNING": 2, "HIGH": 3, "CRITICAL": 4}


def severity_allows(*, event_severity: str, minimum_severity: str) -> bool:
    return _SEVERITY.get(event_severity, -1) >= _SEVERITY.get(minimum_severity, 99)


def route_event(database: Session, event: NotificationEvent, user_id: UUID) -> int:
    """Create idempotent channel routes from preferences with a durable critical web copy."""

    preferences = database.scalars(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.enabled.is_(True),
        )
    ).all()
    enabled = {
        preference.channel
        for preference in preferences
        if severity_allows(
            event_severity=event.severity,
            minimum_severity=preference.minimum_severity,
        )
    }
    plan = route(severity=event.severity, enabled_channels=enabled)
    channels = set(plan.channels)
    if plan.persist_web_inbox:
        channels.add("WEB")
    created = 0
    for channel in sorted(channels):
        existing = database.scalar(
            select(RoutedNotification.id).where(
                RoutedNotification.event_id == event.id,
                RoutedNotification.user_id == user_id,
                RoutedNotification.channel == channel,
            )
        )
        if existing is not None:
            continue
        database.add(
            RoutedNotification(
                event_id=event.id,
                user_id=user_id,
                channel=channel,
                state="PENDING",
                read_at=None,
            )
        )
        created += 1
    database.flush()
    return created
