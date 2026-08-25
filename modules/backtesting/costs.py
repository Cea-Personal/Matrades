from dataclasses import dataclass
from decimal import Decimal

from packages.shared.domain_types import InstrumentType


@dataclass(frozen=True)
class TradingCosts:
    spread: Decimal
    commission: Decimal
    slippage: Decimal
    swap: Decimal = Decimal("0")
    funding: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return sum(
            (self.spread, self.commission, self.slippage, self.swap, self.funding), Decimal("0")
        )


def type_aware_costs(
    instrument_type: InstrumentType,
    *,
    spread: Decimal = Decimal("0"),
    commission: Decimal = Decimal("0"),
    slippage: Decimal = Decimal("0"),
    financing: Decimal = Decimal("0"),
    funding: Decimal = Decimal("0"),
) -> TradingCosts:
    """Normalize costs without treating margin as a maximum loss."""
    if min(spread, commission, slippage, financing, funding) < 0:
        raise ValueError("backtest costs cannot be negative")
    swap = financing if instrument_type is InstrumentType.CFD else Decimal("0")
    return TradingCosts(spread, commission, slippage, swap=swap, funding=funding)
