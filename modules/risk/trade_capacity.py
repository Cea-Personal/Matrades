from decimal import Decimal


def additional_trade_capacity(
    *,
    static_max: int,
    open_trades: int,
    remaining_portfolio_risk: Decimal,
    candidate_risk: Decimal,
    correlated_capacity: Decimal | None = None,
) -> int:
    slots = max(0, static_max - open_trades)
    if slots == 0 or candidate_risk <= 0:
        return 0
    risk_slots = int(max(Decimal("0"), remaining_portfolio_risk) // candidate_risk)
    if correlated_capacity is not None:
        risk_slots = min(risk_slots, int(max(Decimal("0"), correlated_capacity) // candidate_risk))
    return max(0, min(slots, risk_slots))
