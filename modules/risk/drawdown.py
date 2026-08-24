from decimal import Decimal


def total_drawdown(starting_balance: Decimal, current_equity: Decimal) -> Decimal:
    return max(Decimal("0"), starting_balance - current_equity)


def drawdown_percentage(starting_balance: Decimal, current_equity: Decimal) -> Decimal:
    if starting_balance <= 0:
        raise ValueError("starting balance must be positive")
    return total_drawdown(starting_balance, current_equity) / starting_balance * Decimal("100")


def daily_loss(realized_daily_pnl: Decimal, floating_pnl: Decimal) -> Decimal:
    return max(Decimal("0"), -(realized_daily_pnl + min(floating_pnl, Decimal("0"))))
