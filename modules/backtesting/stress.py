import random


def monte_carlo(returns: list[float], runs: int = 100, seed: int = 7) -> dict[str, float]:
    rng = random.Random(seed)  # noqa: S311 - deterministic simulation, not security
    outcomes = (
        [sum(rng.choice(returns) for _ in returns) for _ in range(runs)] if returns else [0.0]
    )
    percentile_index = min(len(outcomes) - 1, max(0, int(len(outcomes) * 0.05) - 1))
    return {"p05": sorted(outcomes)[percentile_index], "worst": min(outcomes)}
