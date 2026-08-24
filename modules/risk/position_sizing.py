from decimal import Decimal

from modules.risk.financial_math import size_for_risk


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
