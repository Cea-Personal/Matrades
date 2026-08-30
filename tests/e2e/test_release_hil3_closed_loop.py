from tests.contract.test_hil3_contract import (
    test_hil3_write_is_disabled_for_autonomous_execution,
)
from tests.contract.test_journal_reconstruction import test_journal_is_append_only_and_idempotent


def test_release_hil3_to_journal():
    test_hil3_write_is_disabled_for_autonomous_execution()
    test_journal_is_append_only_and_idempotent()
