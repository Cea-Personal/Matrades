from pathlib import Path

import pytest

from modules.trading.legacy_compatibility import LegacyWorkflowDisabled, reject_new_write


def test_autonomous_migration_has_reversible_upgrade_and_legacy_write_fence() -> None:
    text = Path("infra/migrations/versions/0012_autonomous_execution.py").read_text()
    assert "def upgrade" in text and "def downgrade" in text
    with pytest.raises(LegacyWorkflowDisabled):
        reject_new_write("manual entry")
