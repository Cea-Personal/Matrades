from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from traderx.audit.model import AuditEvent
from traderx.shared.db import Base, load_model_metadata


def test_audit_model_is_append_only_evidence() -> None:
    assert AuditEvent.__tablename__ == "audit_events"


def _event() -> AuditEvent:
    return AuditEvent.create(
        actor_type="USER",
        actor_id=None,
        actor_role="OWNER",
        action="integration.disable",
        outcome="SUCCEEDED",
        target_type="integration",
        target_id=None,
        target_version=1,
        reason="Disable after a health failure",
        assurance="MFA",
        correlation_id="correlation-1",
        causation_id=None,
        idempotency_key="disable-request-0001",
        previous_value={"state": "HEALTHY"},
        new_value={"state": "DISABLED"},
        occurred_at=datetime(2026, 8, 14, tzinfo=UTC),
    )


def test_audit_integrity_before_after_and_append_only_enforcement() -> None:
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory.begin() as database:
            event = _event()
            database.add(event)
            database.flush()
            event_id = event.id
        with factory() as database:
            event = database.get(AuditEvent, event_id)
            assert event is not None
            assert event.verify_integrity()
            assert event.previous_value == {"state": "HEALTHY"}
            assert event.new_value == {"state": "DISABLED"}
            event.reason = "tampered"
            with pytest.raises(ValueError, match="append-only"):
                database.commit()
            database.rollback()
        with factory() as database:
            event = database.scalar(select(AuditEvent))
            assert event is not None
            database.delete(event)
            with pytest.raises(ValueError, match="append-only"):
                database.commit()
    finally:
        engine.dispose()


def test_mandatory_audit_failure_rolls_back_the_high_risk_change() -> None:
    load_model_metadata()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with pytest.raises(IntegrityError), factory.begin() as database:
            valid = _event()
            database.add(valid)
            database.flush()
            duplicate = _event()
            duplicate.id = valid.id
            database.add(duplicate)
            # The duplicate primary key makes audit persistence fail in the same transaction.
            database.flush()
        with factory() as database:
            assert database.scalar(select(AuditEvent)) is None
    finally:
        engine.dispose()
