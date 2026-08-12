from traderx.instruments.reactivation_service import begin_reactivation
from traderx.strategies.staleness import EvidenceFreshness, RevalidationPlan


def test_replacement_reactivation_preserves_evidence_and_never_autoactivates() -> None:
    outcome = begin_reactivation(RevalidationPlan(EvidenceFreshness.CURRENT, ()))
    assert outcome.state == "AWAITING_HUMAN_APPROVAL"
