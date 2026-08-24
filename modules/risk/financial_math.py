from decimal import Decimal

from packages.shared.domain_types import round_down


def conservative_entry(direction: str, bid: Decimal, ask: Decimal) -> Decimal:
    if bid <= 0 or ask <= 0 or ask < bid:
        raise ValueError("invalid quote")
    return ask if direction == "BUY" else bid


def loss_per_unit(
    entry: Decimal,
    stop: Decimal,
    contract_size: Decimal = Decimal("1"),
    conversion_rate: Decimal = Decimal("1"),
) -> Decimal:
    if min(entry, stop, contract_size, conversion_rate) <= 0:
        raise ValueError("prices, contract size, and conversion must be positive")
    return abs(entry - stop) * contract_size * conversion_rate


def size_for_risk(risk_budget: Decimal, per_unit_loss: Decimal, increment: Decimal) -> Decimal:
    if risk_budget <= 0 or per_unit_loss <= 0:
        return Decimal("0")
    return round_down(risk_budget / per_unit_loss, increment)
