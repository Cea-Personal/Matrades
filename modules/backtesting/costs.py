from dataclasses import dataclass
from decimal import Decimal


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
