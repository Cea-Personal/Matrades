from tests.contract.test_hil3_contract import (
    test_approval_revalidates_policy_and_never_mutates_broker,
)
from tests.contract.test_journal_reconstruction import test_journal_is_append_only_and_idempotent


def test_release_hil3_to_journal():
    test_approval_revalidates_policy_and_never_mutates_broker()
    test_journal_is_append_only_and_idempotent()
