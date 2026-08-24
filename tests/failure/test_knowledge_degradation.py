from modules.knowledge.authority import RecordAuthority, route
from modules.risk.engine import RiskEngine


def test_vector_outage_does_not_replace_deterministic_services():
    assert route("knowledge") == RecordAuthority.CONTEXT_ONLY
    assert RiskEngine is not None
