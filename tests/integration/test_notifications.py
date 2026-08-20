from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.identity.model import Role, User, UserStatus
from traderx.notifications.model import (
    NotificationEvent,
    NotificationPreference,
    RoutedNotification,
)
from traderx.notifications.providers import (
    DeliveryUnavailable,
    EmailProvider,
    TelegramProvider,
    UnconfiguredExternalProvider,
    WebInboxProvider,
)
from traderx.notifications.router import (
    notify_market_research_owners,
    retryable,
    route,
    route_event,
    severity_allows,
)
from traderx.shared.db import Base, load_model_metadata


def test_critical_notification_has_durable_web_inbox_and_bounded_retries() -> None:
    assert route(severity="CRITICAL", enabled_channels={"email"}).persist_web_inbox
    assert retryable(2)
    assert not retryable(3)


def test_delivery_adapters_confirm_receipts_and_fail_closed_when_unconfigured() -> None:
    assert WebInboxProvider().deliver("notice-1", "content").confirmed
    assert (
        EmailProvider(lambda notification_id, _: f"email:{notification_id}")
        .deliver("notice-1", "content")
        .provider_reference
        == "email:notice-1"
    )
    assert (
        TelegramProvider(lambda notification_id, _: f"telegram:{notification_id}")
        .deliver("notice-2", "content")
        .provider_reference
        == "telegram:notice-2"
    )
    with pytest.raises(DeliveryUnavailable, match="not configured"):
        UnconfiguredExternalProvider("EMAIL").deliver("notice-3", "content")


def test_severity_thresholds_are_channel_independent() -> None:
    assert severity_allows(event_severity="CRITICAL", minimum_severity="WARNING")
    assert severity_allows(event_severity="ACTION", minimum_severity="INFO")
    assert not severity_allows(event_severity="INFO", minimum_severity="WARNING")


def test_routing_preferences_are_deduplicated_and_critical_web_copy_is_durable() -> None:
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    user_id = uuid4()
    try:
        with factory.begin() as database:
            database.add_all(
                [
                    NotificationPreference(
                        user_id=user_id,
                        channel="EMAIL",
                        minimum_severity="WARNING",
                        enabled=True,
                    ),
                    NotificationPreference(
                        user_id=user_id,
                        channel="TELEGRAM",
                        minimum_severity="CRITICAL",
                        enabled=False,
                    ),
                ]
            )
            event = NotificationEvent(
                event_type="RISK_LOCKDOWN",
                severity="CRITICAL",
                dedupe_key="risk-lockdown:account-1:snapshot-1",
                payload={"account_id": "account-1"},
                created_at=datetime(2026, 8, 14, tzinfo=UTC),
            )
            database.add(event)
            database.flush()
            assert route_event(database, event, user_id) == 2
            assert route_event(database, event, user_id) == 0

        with factory() as database:
            routes = database.scalars(
                select(RoutedNotification).order_by(RoutedNotification.channel)
            ).all()
            assert [item.channel for item in routes] == ["EMAIL", "WEB"]
            assert all(item.state == "PENDING" for item in routes)
    finally:
        engine.dispose()


def test_ambiguous_delivery_timeout_retries_with_same_notification_identity() -> None:
    seen: list[str] = []

    def ambiguous_sender(notification_id: str, _: str) -> str:
        seen.append(notification_id)
        raise TimeoutError("provider receipt was ambiguous")

    provider = EmailProvider(ambiguous_sender)
    for attempt in (1, 2, 3):
        with pytest.raises(TimeoutError, match="ambiguous"):
            provider.deliver("stable-route-id", "content")
        assert retryable(attempt) is (attempt < 3)
    assert seen == ["stable-route-id"] * 3


def test_market_research_alerts_target_active_owners_and_deduplicate() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 20, 10, tzinfo=UTC)
    with sessionmaker(bind=engine).begin() as database:
        owner_password_digest = str(uuid4())
        viewer_password_digest = str(uuid4())
        owner = User(
            email="owner@example.com",
            password_hash=owner_password_digest,
            role=Role.OWNER,
            status=UserStatus.ACTIVE,
            mfa_required=True,
        )
        viewer = User(
            email="viewer@example.com",
            password_hash=viewer_password_digest,
            role=Role.VIEWER,
            status=UserStatus.ACTIVE,
            mfa_required=True,
        )
        database.add_all([owner, viewer])
        database.flush()
        first = notify_market_research_owners(
            database,
            kind="CATEGORY_BLOCKED",
            subject_id="category-run-1",
            payload={"category": "COMMODITY", "reason": "SOURCE_STALE"},
            created_at=now,
        )
        replay = notify_market_research_owners(
            database,
            kind="CATEGORY_BLOCKED",
            subject_id="category-run-1",
            payload={"category": "COMMODITY", "reason": "SOURCE_STALE"},
            created_at=now,
        )
        assert len(first) == len(replay) == 1
        assert first[0].id == replay[0].id
        assert first[0].payload["user_id"] == str(owner.id)
        assert database.scalars(select(NotificationEvent)).all() == first
