from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class JournalProjection:
    gross_pnl: Decimal
    net_pnl: Decimal
    r_multiple: Decimal | None


def project_trade(
    *,
    entry: Decimal,
    exit: Decimal,
    units: Decimal,
    direction: str,
    costs: Decimal,
    initial_risk: Decimal,
) -> JournalProjection:
    sign = Decimal("1") if direction == "LONG" else Decimal("-1")
    gross = (exit - entry) * units * sign
    net = gross - costs
    return JournalProjection(gross, net, net / initial_risk if initial_risk > 0 else None)
