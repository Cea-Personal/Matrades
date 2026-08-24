from tests.contract.test_hil2_contract import test_take_records_intent_without_execution
from tests.integration.test_position_reconciliation import test_exact_ambiguous_and_no_match


def test_release_hil2_to_manual_reconciliation():
    test_take_records_intent_without_execution()
    test_exact_ambiguous_and_no_match()
