"""Forward candle observation and replayable simulated trading evidence."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from modules.backtesting.engine import (
    BacktestCandle,
    BacktestConfiguration,
    risk_normalized_account_metrics,
)
from modules.backtesting.protection import simulate_protected_trades
from modules.research.sessions import weekend_close
from modules.strategies.entry_context import entry_context_reason
from modules.strategies.pair_profile import news_state
from modules.strategies.trade_setup import build_strategy_setup
from packages.strategy_sdk.schema import StrategySpecification

ENGINE = "forward-paper-v1"
VALIDATION_GATES = ("backtest", "out_of_sample", "walk_forward", "stress", "policy")


def validation_passed(evidence: dict) -> bool:
    return all(evidence.get(gate) for gate in VALIDATION_GATES) and all(
        evidence.get(gate, True)
        for gate in ("parameter_sensitivity", "cost_stress", "event_driven_execution")
    )


def observe(
    spec: StrategySpecification,
    state: dict,
    incoming: list[BacktestCandle],
    *,
    now: datetime,
    timeframe_seconds: int,
    configuration: BacktestConfiguration,
    calendar: list[dict] | None = None,
    paper: bool,
) -> dict:
    """Freeze completed observations; record intents before their outcome candle closes.

    Paper fills use next-bar OHLC simulation. A signal must have been observed
    within five minutes of the entry bar opening to be eligible for a fill.
    Replaying only these persisted intents makes duplicate delivery idempotent.
    """
    period = timedelta(seconds=timeframe_seconds)
    closed = sorted(
        (c for c in incoming if c.observed_at + period <= now), key=lambda c: c.observed_at
    )
    if len(closed) < 6:
        raise ValueError("At least six completed candles are required for monitoring")
    for candle in closed:
        if not all(
            value.is_finite() and value > 0
            for value in (candle.open, candle.high, candle.low, candle.close)
        ):
            raise ValueError("Invalid monitoring price evidence")
        if candle.high < max(candle.open, candle.close, candle.low) or candle.low > min(
            candle.open, candle.close
        ):
            raise ValueError("Inconsistent monitoring OHLC evidence")
    frozen = [BacktestCandle.model_validate(item) for item in state.get("candles", [])]
    new = [c for c in closed if not frozen or c.observed_at > frozen[-1].observed_at]
    if not frozen:
        # Existing history is warmup only. It can never create past paper trades.
        frozen = closed[-100:]
    else:
        frozen += new
    if len(frozen) > 100_000:
        raise ValueError("Paper observation limit reached; finish this session")
    setup = build_strategy_setup(
        spec,
        frozen,
        now=now,
        timeframe_seconds=timeframe_seconds,
        tick_size=configuration.tick_size,
        calendar=calendar,
    )
    reason = entry_context_reason(spec, now, calendar)
    if paper and state.get("data_complete") is False:
        reason = "Paper history has missing observations; start a new validation session"
    if paper and state.get("policy_passed") is False:
        reason = "Paper loss limits were breached; review this session"
    if reason and setup["status"] != "MARKET_CLOSED":
        setup = {
            **setup,
            "status": "BLOCKED",
            "reason": reason,
            "entry": None,
            "stop_loss": None,
            "take_profits": [],
        }
    intents = dict(state.get("entry_intents", {}))
    entry_time = frozen[-1].observed_at + period
    start = datetime.fromisoformat(state["started_at"])
    cutoff = datetime.fromisoformat(state["entry_cutoff"]) if state.get("entry_cutoff") else None
    output = {
        **state,
        "last_checked_at": now.isoformat(),
        "latest_signal": setup,
        "last_candle_at": frozen[-1].observed_at.isoformat(),
    }
    if not paper:
        return output
    news_contexts = dict(state.get("news_contexts", {}))
    if start <= entry_time and 0 <= (now - entry_time).total_seconds() <= min(
        300, timeframe_seconds / 4
    ):
        news_contexts.setdefault(
            entry_time.isoformat(), news_state(spec.instruments[0], now, calendar)
        )
    # If a captured entry or open trade spans missing bars, evidence cannot pass.
    missing = False
    for before, after in zip(frozen, frozen[1:], strict=False):
        if after.observed_at - before.observed_at > period and after.observed_at >= start:
            cursor = before.observed_at + period
            while cursor < after.observed_at:
                closed_session = weekend_close(spec.asset_class, cursor) is not None
                if spec.asset_class == "STOCKS":
                    local = cursor.astimezone(ZoneInfo("America/New_York"))
                    closed_session = (
                        local.weekday() >= 5 or not 570 <= local.hour * 60 + local.minute < 960
                    )
                if not closed_session:
                    missing = True
                    break
                cursor += period
    positions: list[dict] = []
    trades, fills, _costs = simulate_protected_trades(
        spec,
        frozen,
        configuration,
        close_at_end=False,
        allowed_entry_times=set(intents),
        open_positions=positions,
        calendar=calendar,
        news_contexts=news_contexts,
    )
    # Persist the decision before its outcome candle closes, only when flat.
    if (
        not positions
        and setup["status"] == "SIGNAL"
        and not missing
        and start <= entry_time
        and (cutoff is None or entry_time < cutoff)
        and 0 <= (now - entry_time).total_seconds() <= min(300, timeframe_seconds / 4)
    ):
        intents.setdefault(
            entry_time.isoformat(), {"observed_at": now.isoformat(), "signal": setup}
        )
    if positions:
        output["latest_signal"] = {
            **setup,
            "status": "POSITION_OPEN",
            "reason": "Managing the existing simulated position",
            "entry": None,
            "stop_loss": None,
            "take_profits": [],
        }
    elif cutoff and now >= cutoff:
        output["latest_signal"] = {
            **setup,
            "status": "WAIT",
            "reason": "Observation window ended; review the paper results",
            "entry": None,
            "stop_loss": None,
            "take_profits": [],
        }
    account = risk_normalized_account_metrics(
        trades,
        [str(fill["exited_at"]) for fill in fills],
        configuration,
        spec.risk_per_trade,
    )
    for fill, pnl in zip(fills, account["account_pnls"], strict=True):
        fill["simulation_account_pnl"] = str(pnl)
    policy = bool(account["policy_passed"])
    if not policy or missing:
        # Do not retain a new entry after discovering a breach on this tick.
        if entry_time.isoformat() not in state.get("entry_intents", {}):
            intents.pop(entry_time.isoformat(), None)
        output["latest_signal"] = {
            **setup,
            "status": "BLOCKED",
            "reason": "Paper loss limits were breached"
            if not policy
            else "Paper observations are incomplete",
            "entry": None,
            "stop_loss": None,
            "take_profits": [],
        }
    pending = [time for time in intents if datetime.fromisoformat(time) > frozen[-1].observed_at]
    output.update(
        {
            "engine": ENGINE,
            "candles": [c.model_dump(mode="json") for c in frozen],
            "entry_intents": intents,
            "news_contexts": news_contexts,
            "trades": fills,
            "open_positions": positions,
            "pending_entries": pending,
            "trade_count": len(trades),
            "net_profit": str(account["net_profit"]),
            "profit_factor": (
                str(account["gross_profit"] / account["gross_loss"])
                if account["gross_loss"]
                else None
            ),
            "gross_profit": str(account["gross_profit"]),
            "gross_loss": str(account["gross_loss"]),
            "max_drawdown": str(account["max_drawdown"]),
            "ending_equity": str(account["ending_equity"]),
            "policy_passed": policy,
            "data_complete": state.get("data_complete", True) and not missing,
            "metrics_units": "SIMULATED_ACCOUNT_RISK_NORMALIZED",
            "execution_authorized": False,
        }
    )
    return output


def paper_gates(data: dict) -> dict[str, bool]:
    return {
        "forward_observation": data.get("engine") == ENGINE,
        "minimum_trade_count": data.get("trade_count", 0) >= 10,
        "positive_net_profit": Decimal(str(data.get("net_profit", "0"))) > 0,
        "profit_factor": Decimal(str(data.get("gross_profit", "0"))) > 0
        and Decimal(str(data.get("gross_profit", "0")))
        >= Decimal(str(data.get("gross_loss", "0"))),
        "policy": data.get("policy_passed") is True,
        "data_complete": data.get("data_complete") is True,
        "positions_closed": not data.get("open_positions") and not data.get("pending_entries"),
    }
