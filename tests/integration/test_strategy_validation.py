from modules.backtesting.promotion import promotable


def test_every_stage_is_required_for_promotion():
    evidence = {
        x: True for x in ("backtest", "out_of_sample", "walk_forward", "stress", "policy", "paper")
    }
    assert promotable(evidence)
    evidence["paper"] = False
    assert not promotable(evidence)
