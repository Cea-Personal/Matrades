from tests.contract.test_risk_api import test_risk_decision_contracts
from tests.integration.test_risk_reservation_concurrency import (
    test_concurrent_candidates_cannot_oversubscribe,
)
from tests.property.test_risk_invariants import test_tighter_portfolio_capacity_never_increases_size


def test_release_risk_controls():
    test_risk_decision_contracts()
    test_tighter_portfolio_capacity_never_increases_size()
    test_concurrent_candidates_cannot_oversubscribe()
