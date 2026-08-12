from datetime import UTC, datetime
from uuid import uuid4

from traderx.shared.events import event_envelope
from traderx.shared.idempotency import IdempotencyConflict, canonical_request_hash


def test_event_envelope_has_correlation_and_aggregate_version() -> None:
    envelope = event_envelope(
        source="urn:traderx:test",
        event_type="com.traderx.test.v1",
        subject="tests/1",
        data={"safe": True},
        now=datetime(2026, 8, 12, tzinfo=UTC),
        correlation_id="correlation",
        actor_id=uuid4(),
        aggregate_version=2,
    )
    assert envelope["aggregateversion"] == 2
    assert envelope["correlationid"] == "correlation"


def test_idempotency_hash_is_order_independent() -> None:
    assert canonical_request_hash({"a": 1, "b": 2}) == canonical_request_hash({"b": 2, "a": 1})


def test_conflicting_idempotency_key_has_dedicated_error() -> None:
    error = IdempotencyConflict("duplicate")
    assert error.status_code == 409
