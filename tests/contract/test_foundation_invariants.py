from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from modules.credentials.redaction import redact
from modules.identity.authorization import Actor, Role
from packages.contracts.events import EventEnvelope
from packages.shared.domain_types import round_down
from packages.shared.idempotency import IdempotencyStore
from packages.shared.redis import EphemeralState


def test_financial_values_round_down_conservatively() -> None:
    assert round_down(Decimal("1.237"), Decimal("0.01")) == Decimal("1.23")


def test_event_envelope_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError):
        EventEnvelope(
            event_type="test",
            occurred_at=datetime(2025, 1, 1),
            owner_id=uuid4(),
            aggregate_id=uuid4(),
            aggregate_version=1,
            payload={},
        )


def test_event_envelope_is_immutable_and_versioned() -> None:
    event = EventEnvelope(
        event_type="test",
        occurred_at=datetime.now(UTC),
        owner_id=uuid4(),
        aggregate_id=uuid4(),
        aggregate_version=2,
        payload={"ok": True},
    )
    assert event.event_version == 1
    with pytest.raises(ValidationError):
        event.payload = {}  # type: ignore[misc]


def test_idempotency_replays_only_identical_requests() -> None:
    store: IdempotencyStore[int] = IdempotencyStore()
    assert store.remember("owner", "key", b"same", 1) == 1
    assert store.remember("owner", "key", b"same", 2) == 1
    with pytest.raises(ValueError):
        store.remember("owner", "key", b"different", 3)


def test_redaction_is_recursive_and_prompt_safe() -> None:
    assert redact(
        {"api_key": "raw", "nested": [{"password": "raw"}], "text": "Bearer abc.xyz"}
    ) == {
        "api_key": "[REDACTED]",
        "nested": [{"password": "[REDACTED]"}],
        "text": "Bearer [REDACTED]",
    }


def test_owner_authorization_is_closed_by_default() -> None:
    actor = Actor(uuid4(), uuid4(), Role.OWNER)
    with pytest.raises(PermissionError):
        actor.require(Role.OWNER, owner_id=uuid4())


def test_redis_wrapper_declares_non_authority() -> None:
    assert EphemeralState.authoritative is False
