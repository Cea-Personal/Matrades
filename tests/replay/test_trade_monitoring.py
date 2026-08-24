from uuid import uuid4

from modules.trading.monitor_agent import interpret


def test_identical_monitor_facts_replay_identically():
    trade = uuid4()
    facts = {"actionable": False, "reason": "stale"}
    left, right = interpret(trade, facts), interpret(trade, facts)
    assert left.model_dump(exclude={"id"}) == right.model_dump(exclude={"id"})
