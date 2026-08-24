from modules.knowledge.authority import RecordAuthority, route


def test_semantic_context_cannot_supply_authoritative_records():
    for record in (
        "account",
        "market_observation",
        "policy",
        "risk_result",
        "performance",
        "strategy_fingerprint",
    ):
        assert route(record) == RecordAuthority.STRUCTURED
    assert route("playbook") == RecordAuthority.CONTEXT_ONLY
