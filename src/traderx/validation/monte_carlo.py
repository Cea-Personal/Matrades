from __future__ import annotations

import random
from decimal import Decimal


def bootstrap_terminal_pnls(pnls: list[Decimal], *, trials: int, seed: int) -> list[Decimal]:
    if not pnls or trials < 1:
        raise ValueError("Monte Carlo needs outcomes and at least one trial")
    # This is an explicitly deterministic analytical bootstrap, not a security boundary.
    randomizer = random.Random(seed)  # noqa: S311
    return [sum((randomizer.choice(pnls) for _ in pnls), Decimal("0")) for _ in range(trials)]
