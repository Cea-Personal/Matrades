import pytest

from modules.trading.legacy_compatibility import LegacyWorkflowDisabled, reject_new_write


def test_legacy_writes_are_rejected() -> None:
    with pytest.raises(LegacyWorkflowDisabled):
        reject_new_write("HIL-2 decisions")
