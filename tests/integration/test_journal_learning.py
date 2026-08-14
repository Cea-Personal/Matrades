from traderx.journal.analytics import ANALYTICS_DIMENSIONS, aggregate
from traderx.journal.hypotheses import propose
from traderx.journal.service import checksum, superseding_annotation


def test_analytics_and_hypotheses_do_not_mutate_source_strategy() -> None:
    result = aggregate([{"instrument": "X", "net_pnl": "2", "r_multiple": "1"}], "instrument")
    assert result["X"]["net_pnl"] == 2
    assert (
        propose(text="test filters", evidence_links=["journal:1"], strategy_version_id="v1").state
        == "PROPOSED"
    )


def test_annotations_attachments_and_every_required_dimension_preserve_sources() -> None:
    row = {
        "instrument": "EURUSD",
        "asset_class": "FOREX",
        "source_type": "RECOMMENDED",
        "strategy_version": "v1",
        "time": "2026-08",
        "direction": "LONG",
        "risk": "LOW",
        "regime": "TREND",
        "entry_quality": "A",
        "behavior": "PLAN_FOLLOWED",
        "net_pnl": "10",
        "r_multiple": "1",
    }
    assert all(aggregate([row], dimension) for dimension in ANALYTICS_DIMENSIONS)
    annotation = superseding_annotation("annotation-1", "Reviewed after the session")
    assert annotation["supersedes_id"] == "annotation-1"
    assert len(checksum(b"protected screenshot")) == 64
    source_strategy = {"lifecycle": "LIVE", "definition_hash": "frozen"}
    proposal = propose(
        text="Test a narrower entry window",
        evidence_links=["journal:1"],
        strategy_version_id="v1",
    )
    assert proposal.state == "PROPOSED"
    assert source_strategy == {"lifecycle": "LIVE", "definition_hash": "frozen"}
