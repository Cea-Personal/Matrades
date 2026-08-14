from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.pool import StaticPool

from traderx.integrations.model import Integration
from traderx.shared.db import Base, load_model_metadata
from traderx.shared.events import ConsumerReceipt, OutboxEvent
from traderx.shared.idempotency import IdempotencyConflict, canonical_request_hash, start_or_replay
from traderx_worker.runtime.outbox import claim_pending


def test_idempotency_hash_is_stable_and_conflicting_replay_is_rejected() -> None:
    assert canonical_request_hash({"a": 1}) == canonical_request_hash({"a": 1})
    with pytest.raises(IdempotencyConflict):
        start_or_replay(
            type("Record", (), {"request_hash": "different", "state": "COMPLETED"})(),
            canonical_request_hash({"a": 1}),
        )


def _factory():  # type: ignore[no-untyped-def]
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False), engine


def test_concurrent_high_risk_updates_reject_the_losing_writer() -> None:
    factory, engine = _factory()
    try:
        with factory.begin() as database:
            integration = Integration(
                name="Concurrent integration",
                provider="WEB_INBOX",
                category="NOTIFICATION",
                state="DISABLED",
                capabilities=["NOTIFICATION_SEND"],
                configuration={},
                official_source=True,
            )
            database.add(integration)
            database.flush()
            integration_id = integration.id
        first, second = factory(), factory()
        try:
            first_copy = first.get(Integration, integration_id)
            second_copy = second.get(Integration, integration_id)
            assert first_copy is not None and second_copy is not None
            first_copy.state = "DEGRADED"
            first.commit()
            second_copy.state = "HEALTHY"
            with pytest.raises(StaleDataError):
                second.commit()
        finally:
            first.close()
            second.close()
    finally:
        engine.dispose()


def test_duplicate_consumer_event_is_rejected_and_outbox_preserves_aggregate_order() -> None:
    factory, engine = _factory()
    aggregate_id = uuid4()
    try:
        with factory.begin() as database:
            database.add_all(
                [
                    OutboxEvent(
                        aggregate_type="strategy",
                        aggregate_id=aggregate_id,
                        aggregate_version=2,
                        event_type="com.traderx.strategy.updated.v1",
                        envelope={"aggregateversion": 2},
                    ),
                    OutboxEvent(
                        aggregate_type="strategy",
                        aggregate_id=aggregate_id,
                        aggregate_version=1,
                        event_type="com.traderx.strategy.created.v1",
                        envelope={"aggregateversion": 1},
                    ),
                    ConsumerReceipt(
                        consumer_name="projection",
                        event_source="urn:traderx",
                        event_id="same-event",
                        outcome="APPLIED",
                    ),
                ]
            )
        with factory() as database:
            claimed = claim_pending(database)
            assert [event.aggregate_version for event in claimed] == [1, 2]
        with pytest.raises(IntegrityError), factory.begin() as database:
            database.add(
                ConsumerReceipt(
                    consumer_name="projection",
                    event_source="urn:traderx",
                    event_id="same-event",
                    outcome="APPLIED_AGAIN",
                )
            )
            database.flush()
    finally:
        engine.dispose()
