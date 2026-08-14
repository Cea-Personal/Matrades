from __future__ import annotations

import random
from decimal import Decimal
from enum import StrEnum


class BootstrapMode(StrEnum):
    SEQUENCE = "SEQUENCE"
    BLOCK = "BLOCK"
    REGIME = "REGIME"


def bootstrap_terminal_pnls(pnls: list[Decimal], *, trials: int, seed: int) -> list[Decimal]:
    if not pnls or trials < 1:
        raise ValueError("Monte Carlo needs outcomes and at least one trial")
    # This is an explicitly deterministic analytical bootstrap, not a security boundary.
    randomizer = random.Random(seed)  # noqa: S311
    return [sum((randomizer.choice(pnls) for _ in pnls), Decimal("0")) for _ in range(trials)]


def stressed_bootstrap(
    pnls: list[Decimal],
    *,
    trials: int,
    seed: int,
    mode: BootstrapMode = BootstrapMode.SEQUENCE,
    block_size: int = 5,
    cost_stress: Decimal = Decimal("0"),
    gap_stress: Decimal = Decimal("0"),
) -> list[Decimal]:
    if not pnls or trials < 1 or block_size < 1 or min(cost_stress, gap_stress) < 0:
        raise ValueError("Monte Carlo configuration is invalid")
    randomizer = random.Random(seed)  # noqa: S311
    results: list[Decimal] = []
    negative = [value for value in pnls if value < 0] or pnls
    for _ in range(trials):
        if mode == BootstrapMode.BLOCK:
            sampled: list[Decimal] = []
            while len(sampled) < len(pnls):
                start = randomizer.randrange(len(pnls))
                sampled.extend(pnls[(start + offset) % len(pnls)] for offset in range(block_size))
            sampled = sampled[: len(pnls)]
        elif mode == BootstrapMode.REGIME:
            sampled = [randomizer.choice(negative if index % 3 == 0 else pnls) for index in range(len(pnls))]
        else:
            sampled = [randomizer.choice(pnls) for _ in pnls]
        stress = (cost_stress * Decimal(len(sampled))) + gap_stress
        results.append(sum(sampled, Decimal("0")) - stress)
    return results
