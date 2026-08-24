from decimal import Decimal

from modules.risk.models import OpenPositionRisk


def reserved_risk(
    positions: list[OpenPositionRisk], include_unrealized_profit: bool = False
) -> Decimal:
    total = Decimal("0")
    for position in positions:
        if position.remaining_loss_to_stop is None:
            raise ValueError(f"unbounded risk for {position.instrument}")
        total += max(Decimal("0"), position.remaining_loss_to_stop)
        if include_unrealized_profit:
            total = max(Decimal("0"), total - max(position.unrealized_pnl, Decimal("0")))
    return total
