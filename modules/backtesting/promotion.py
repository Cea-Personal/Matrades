def promotable(evidence: dict[str, bool]) -> bool:
    return bool(evidence) and all(
        evidence.get(stage, False)
        for stage in ("backtest", "out_of_sample", "walk_forward", "stress", "policy", "paper")
    )


def typed_promotable(evidence: dict[str, bool], *, profile_complete: bool) -> bool:
    """Promotion requires all validation gates and a complete typed profile."""
    return profile_complete and promotable(evidence)
