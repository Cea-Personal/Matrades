import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent


def test_migration_chain_is_linear_and_uses_governed_retention() -> None:
    revisions = sorted(Path("migrations/versions").glob("*.py"))
    assert len(revisions) >= 10
    assert all("revision =" in path.read_text() for path in revisions)
    assert len({path.stem.split("_", maxsplit=1)[0] for path in revisions}) == len(revisions)
    revision_ids = [
        match.group(1)
        for path in revisions
        if (match := re.search(r'^revision = "([^"]+)"', path.read_text(), re.MULTILINE))
    ]
    assert len(revision_ids) == len(revisions)
    assert all(len(revision_id) <= 32 for revision_id in revision_ids)


def test_fresh_forward_migration_reaches_head_and_downgrade_preserves_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "migration-rehearsal.sqlite3"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("script_location", str(Path("migrations").resolve()))
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {
            "alembic_version",
            "audit_events",
            "journal_entries",
            "integrations",
            "provider_catalogue_entries",
            "market_research_schedules",
            "market_research_occurrences",
            "coordinated_market_research_runs",
            "llm_analysis_attempts",
        } <= tables
        with engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == (
                "0025_research_leases"
            )
        with Session(engine) as database:
            event = AuditEvent.create(
                actor_type="SYSTEM",
                actor_id=None,
                actor_role=None,
                action="migration.rehearsal",
                outcome="SUCCEEDED",
                target_type="database",
                target_id=None,
                target_version=None,
                reason="Prove governed evidence survives a prohibited downgrade",
                assurance=None,
                correlation_id="migration-rehearsal",
                causation_id=None,
                idempotency_key=None,
                previous_value=None,
                new_value={"revision": "0025_research_leases"},
                occurred_at=datetime(2026, 8, 14, tzinfo=UTC),
            )
            database.add(event)
            database.commit()
            event_id = event.id

        with pytest.raises(RuntimeError, match="evidence must be retained"):
            command.downgrade(config, "-1")
        with Session(engine) as database:
            retained = database.scalar(select(AuditEvent).where(AuditEvent.id == event_id))
            assert retained is not None
            assert retained.verify_integrity()
    finally:
        engine.dispose()
