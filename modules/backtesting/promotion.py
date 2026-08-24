def promotable(evidence: dict[str, bool]) -> bool:
    return bool(evidence) and all(
        evidence.get(stage, False)
        for stage in ("backtest", "out_of_sample", "walk_forward", "stress", "policy", "paper")
    )
