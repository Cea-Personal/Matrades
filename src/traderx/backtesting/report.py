from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.backtesting.engine import SimulatedTrade


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    net_pnl: Decimal
    win_rate: Decimal
    average_r: Decimal
    maximum_drawdown: Decimal
    trades: int


def report(
    trades: list[SimulatedTrade], *, initial_equity: Decimal, risk_per_trade: Decimal
) -> BacktestMetrics:
    if risk_per_trade <= 0:
        raise ValueError("risk per trade must be positive")
    pnl = [trade.pnl for trade in trades]
    equity = initial_equity
    peak = equity
    drawdown = Decimal("0")
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    wins = sum(1 for value in pnl if value > 0)
    return BacktestMetrics(
        sum(pnl, Decimal("0")),
        Decimal(wins) / max(1, len(pnl)),
        sum((value / risk_per_trade for value in pnl), Decimal("0")) / max(1, len(pnl)),
        drawdown,
        len(trades),
    )
