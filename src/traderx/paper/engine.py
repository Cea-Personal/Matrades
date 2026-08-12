from __future__ import annotations

from decimal import Decimal

from traderx.backtesting.engine import Bar, SimulatedTrade, replay
from traderx.backtesting.execution import FillPolicy


def simulate_current_data(
    bars: list[Bar],
    *,
    direction: str,
    units: Decimal,
    stop: Decimal,
    target: Decimal,
    policy: FillPolicy,
) -> list[SimulatedTrade]:
    """Paper trading deliberately uses the same canonical execution engine as validation."""
    return replay(bars, direction=direction, units=units, policy=policy, stop=stop, target=target)
