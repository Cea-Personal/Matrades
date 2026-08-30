from pathlib import Path

from modules.trading.models import ExecutionCommand
from packages.contracts.events import EventEnvelope


def test_autonomous_migration_preserves_legacy_tables_and_adds_command_state() -> None:
    migration = Path("infra/migrations/versions/0012_autonomous_execution.py").read_text()
    assert "execution_commands" in migration
    assert "execution_attempts" in migration
    assert "legacy" in migration.lower()


def test_event_envelopes_and_commands_have_owner_and_identity_boundaries() -> None:
    assert "owner_id" in EventEnvelope.model_fields
    assert {"account_id", "idempotency_key"} <= set(ExecutionCommand.model_fields)
