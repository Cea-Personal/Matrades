from modules.backtesting.promotion import typed_promotable


def test_strategy_promotion_requires_paper_evidence_and_typed_profile() -> None:
    evidence = {
        stage: True
        for stage in ("backtest", "out_of_sample", "walk_forward", "stress", "policy", "paper")
    }
    assert typed_promotable(evidence, profile_complete=False) is False
    assert typed_promotable(evidence, profile_complete=True) is True
