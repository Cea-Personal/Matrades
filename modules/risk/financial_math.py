from decimal import Decimal

from packages.shared.domain_types import InstrumentType, round_down


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


def type_aware_loss_per_unit(
    *,
    instrument_type: InstrumentType,
    entry: Decimal,
    stop: Decimal,
    contract_multiplier: Decimal = Decimal("1"),
    tick_size: Decimal | None = None,
    tick_value: Decimal | None = None,
    conversion_rate: Decimal = Decimal("1"),
) -> Decimal:
    """Return worst-case loss for one native quantity unit."""
    if conversion_rate <= 0 or contract_multiplier <= 0:
        raise ValueError("conversion and contract multiplier must be positive")
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("entry and stop must differ")
    if instrument_type is InstrumentType.FUTURES:
        if tick_size is None or tick_value is None or tick_size <= 0 or tick_value <= 0:
            raise ValueError("futures require positive tick size and tick value")
        ticks = (distance / tick_size).copy_abs()
        return ticks * tick_value * conversion_rate
    return distance * contract_multiplier * conversion_rate


def notional_exposure(
    *,
    instrument_type: InstrumentType,
    price: Decimal,
    quantity: Decimal,
    contract_multiplier: Decimal = Decimal("1"),
) -> Decimal:
    if min(price, quantity, contract_multiplier) <= 0:
        raise ValueError("price, quantity, and multiplier must be positive")
    return price * quantity * contract_multiplier
