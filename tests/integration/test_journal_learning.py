from traderx.journal.analytics import aggregate
from traderx.journal.hypotheses import propose


def test_analytics_and_hypotheses_do_not_mutate_source_strategy() -> None:
    result = aggregate([{"instrument": "X", "net_pnl": "2", "r_multiple": "1"}], "instrument")
    assert result["X"]["net_pnl"] == 2
    assert (
        propose(text="test filters", evidence_links=["journal:1"], strategy_version_id="v1").state
        == "PROPOSED"
    )
