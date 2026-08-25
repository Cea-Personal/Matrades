from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from modules.market_data.models import CorporateAction, FuturesContract


@dataclass(frozen=True)
class TradeResult:
    pnl: Decimal
    risk: Decimal
    mae: Decimal
    mfe: Decimal


def metrics(trades: list[TradeResult]) -> dict[str, Decimal]:
    if not trades:
        return {
            key: Decimal("0")
            for key in (
                "trade_count",
                "win_rate",
                "expectancy",
                "r",
                "max_drawdown",
                "average_winner",
                "average_loser",
                "profit_factor",
                "mae",
                "mfe",
                "max_win_streak",
                "max_loss_streak",
            )
        }
    equity = peak = Decimal("0")
    max_dd = Decimal("0")
    winners = [trade.pnl for trade in trades if trade.pnl > 0]
    losers = [trade.pnl for trade in trades if trade.pnl < 0]
    win_streak = loss_streak = max_win_streak = max_loss_streak = 0
    for trade in trades:
        equity += trade.pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if trade.pnl > 0:
            win_streak += 1
            loss_streak = 0
        elif trade.pnl < 0:
            loss_streak += 1
            win_streak = 0
        max_win_streak = max(max_win_streak, win_streak)
        max_loss_streak = max(max_loss_streak, loss_streak)
    gross_profit = sum(winners, Decimal("0"))
    gross_loss = abs(sum(losers, Decimal("0")))
    return {
        "trade_count": Decimal(len(trades)),
        "win_rate": Decimal(len(winners)) / Decimal(len(trades)),
        "expectancy": sum((t.pnl for t in trades), Decimal("0")) / len(trades),
        "r": sum((t.pnl / t.risk for t in trades if t.risk > 0), Decimal("0")) / len(trades),
        "max_drawdown": max_dd,
        "average_winner": gross_profit / len(winners) if winners else Decimal("0"),
        "average_loser": sum(losers, Decimal("0")) / len(losers) if losers else Decimal("0"),
        "profit_factor": gross_profit / gross_loss if gross_loss else Decimal("0"),
        "mae": sum((t.mae for t in trades), Decimal("0")) / len(trades),
        "mfe": sum((t.mfe for t in trades), Decimal("0")) / len(trades),
        "max_win_streak": Decimal(max_win_streak),
        "max_loss_streak": Decimal(max_loss_streak),
    }


def lifecycle_adjustment(action: CorporateAction, quantity: Decimal) -> Decimal:
    if action.action_type in {"DIVIDEND", "CASH_ADJUSTMENT"}:
        return quantity * (action.cash_amount or Decimal("0"))
    return Decimal("0")


def roll_reference(previous: FuturesContract, next_contract: FuturesContract) -> dict[str, str]:
    if previous.series_id != next_contract.series_id:
        raise ValueError("futures roll must remain within one series")
    return {
        "from_contract_id": str(previous.id),
        "to_contract_id": str(next_contract.id),
        "from_code": previous.contract_code,
        "to_code": next_contract.contract_code,
    }
