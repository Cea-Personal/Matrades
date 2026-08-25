from decimal import Decimal

from modules.risk.financial_math import size_for_risk, type_aware_loss_per_unit
from packages.shared.domain_types import InstrumentType


def compliant_size(
    requested_size: Decimal,
    risk_per_unit: Decimal,
    remaining_capacities: list[Decimal],
    increment: Decimal,
) -> Decimal:
    if not remaining_capacities:
        return requested_size
    budget = max(Decimal("0"), min(remaining_capacities))
    return min(requested_size, size_for_risk(budget, risk_per_unit, increment))


def compliant_typed_size(
    *,
    requested_size: Decimal,
    risk_budget: Decimal,
    instrument_type: InstrumentType,
    entry: Decimal,
    stop: Decimal,
    increment: Decimal,
    contract_multiplier: Decimal = Decimal("1"),
    tick_size: Decimal | None = None,
    tick_value: Decimal | None = None,
    conversion_rate: Decimal = Decimal("1"),
) -> Decimal:
    per_unit = type_aware_loss_per_unit(
        instrument_type=instrument_type,
        entry=entry,
        stop=stop,
        contract_multiplier=contract_multiplier,
        tick_size=tick_size,
        tick_value=tick_value,
        conversion_rate=conversion_rate,
    )
    return min(requested_size, size_for_risk(risk_budget, per_unit, increment))
