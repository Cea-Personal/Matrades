from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.backtesting.engine import SimulatedTrade
from traderx.shared.types import floor_to_step


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    net_pnl: Decimal
    win_rate: Decimal
    average_r: Decimal
    maximum_drawdown: Decimal
    trades: int
    gross_pnl: Decimal = Decimal("0")
    total_costs: Decimal = Decimal("0")
    profit_factor: Decimal | None = None
    maximum_mae: Decimal = Decimal("0")
    maximum_mfe: Decimal = Decimal("0")
    equity_curve: tuple[Decimal, ...] = ()
    r_distribution: tuple[Decimal, ...] = ()


def report(
    trades: list[SimulatedTrade], *, initial_equity: Decimal, risk_per_trade: Decimal
) -> BacktestMetrics:
    if risk_per_trade <= 0:
        raise ValueError("risk per trade must be positive")
    pnl = [trade.pnl for trade in trades]
    equity = initial_equity
    equity_curve = [equity]
    peak = equity
    drawdown = Decimal("0")
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        equity_curve.append(equity)
    wins = sum(1 for value in pnl if value > 0)
    gross_wins = sum((value for value in pnl if value > 0), Decimal("0"))
    gross_losses = abs(sum((value for value in pnl if value < 0), Decimal("0")))
    r_values = tuple(value / risk_per_trade for value in pnl)
    return BacktestMetrics(
        sum(pnl, Decimal("0")),
        Decimal(wins) / max(1, len(pnl)),
        sum((value / risk_per_trade for value in pnl), Decimal("0")) / max(1, len(pnl)),
        drawdown,
        len(trades),
        gross_pnl=sum((trade.gross_pnl for trade in trades), Decimal("0")),
        total_costs=sum((trade.costs for trade in trades), Decimal("0")),
        profit_factor=(gross_wins / gross_losses if gross_losses > 0 else None),
        maximum_mae=max((trade.mae for trade in trades), default=Decimal("0")),
        maximum_mfe=max((trade.mfe for trade in trades), default=Decimal("0")),
        equity_curve=tuple(equity_curve),
        r_distribution=r_values,
    )


def exact_risk_units(
    *,
    equity: Decimal,
    risk_fraction: Decimal,
    stop_distance: Decimal,
    value_per_price_unit: Decimal,
    volume_step: Decimal,
) -> Decimal:
    if min(equity, risk_fraction, stop_distance, value_per_price_unit, volume_step) <= 0:
        raise ValueError("position sizing inputs must be positive")
    requested = equity * risk_fraction / (stop_distance * value_per_price_unit)
    return floor_to_step(requested, volume_step)
