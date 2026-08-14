from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from traderx.risk.calculator import RiskInputs, RiskResult, calculate_risk
from traderx.shared.types import RiskState

_UNBOUNDED_LOSS_LIMIT = Decimal("1E+28")


@dataclass(frozen=True, slots=True)
class PortfolioRules:
    prop_daily_loss_limit: Decimal = _UNBOUNDED_LOSS_LIMIT
    internal_daily_loss_limit: Decimal = _UNBOUNDED_LOSS_LIMIT
    prop_drawdown_limit: Decimal = _UNBOUNDED_LOSS_LIMIT
    internal_drawdown_limit: Decimal = _UNBOUNDED_LOSS_LIMIT
    minimum_prop_buffer: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        limits = (
            self.prop_daily_loss_limit,
            self.internal_daily_loss_limit,
            self.prop_drawdown_limit,
            self.internal_drawdown_limit,
        )
        if any(limit <= 0 for limit in limits) or self.minimum_prop_buffer < 0:
            raise ValueError("portfolio prop and internal limits must be positive")
        if self.minimum_prop_buffer >= min(
            self.prop_daily_loss_limit, self.prop_drawdown_limit
        ):
            raise ValueError("minimum prop buffer must leave positive loss capacity")


@dataclass(frozen=True, slots=True)
class PortfolioSignal:
    id: str
    score: Decimal
    risk: Decimal
    correlation_to_open: Decimal
    common_exposure: str | None = None
    occurred_at: datetime | None = None
    closed_at: datetime | None = None
    realized_pl: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class PortfolioSimulation:
    selected: tuple[PortfolioSignal, ...]
    blocked: tuple[tuple[str, str], ...]
    peak_open_risk: Decimal
    prop_breach: bool
    peak_open_positions: int = 0
    final_risk_state: RiskState = RiskState.NORMAL
    risk_states: tuple[tuple[datetime | None, RiskState], ...] = ()
    realized_daily_loss: Decimal = Decimal("0")
    realized_drawdown: Decimal = Decimal("0")


def select_signals(
    signals: list[PortfolioSignal], *, capacity: int, correlation_limit: Decimal
) -> list[PortfolioSignal]:
    if capacity < 0 or capacity > 2:
        raise ValueError("TraderX capacity is bounded from zero through two")
    return [
        signal
        for signal in sorted(signals, key=lambda item: item.score, reverse=True)
        if signal.correlation_to_open <= correlation_limit
    ][:capacity]


def simulate_shared_account(
    signals: list[PortfolioSignal],
    *,
    capacity: int,
    correlation_limit: Decimal,
    maximum_open_risk: Decimal,
    rules: PortfolioRules | None = None,
    initial_daily_loss: Decimal = Decimal("0"),
    initial_drawdown: Decimal = Decimal("0"),
) -> PortfolioSimulation:
    if (
        capacity < 0
        or capacity > 2
        or maximum_open_risk < 0
        or initial_daily_loss < 0
        or initial_drawdown < 0
    ):
        raise ValueError("portfolio simulation limits are invalid")
    for signal in signals:
        if signal.risk < 0:
            raise ValueError("portfolio signal risk cannot be negative")
        if (
            signal.occurred_at is not None
            and signal.closed_at is not None
            and signal.closed_at < signal.occurred_at
        ):
            raise ValueError("portfolio signal cannot close before it occurs")
    applied_rules = rules or PortfolioRules()
    ordered = sorted(signals, key=_signal_order)
    selected: list[PortfolioSignal] = []
    blocked: list[tuple[str, str]] = []
    active: dict[str, PortfolioSignal] = {}
    open_risk = Decimal("0")
    peak_open_risk = Decimal("0")
    peak_open_positions = 0
    daily_loss = initial_daily_loss
    drawdown = initial_drawdown
    risk_states: list[tuple[datetime | None, RiskState]] = []
    prop_breach = False

    def settle_due_signals(instant: datetime | None) -> None:
        nonlocal open_risk, daily_loss, drawdown
        closing = sorted(
            (
                item
                for item in active.values()
                if item.closed_at is not None
                and instant is not None
                and item.closed_at <= instant
            ),
            key=lambda item: (item.closed_at, item.id),
        )
        for item in closing:
            active.pop(item.id)
            open_risk -= item.risk
            if item.realized_pl < 0:
                loss = abs(item.realized_pl)
                daily_loss += loss
                drawdown += loss
            elif item.realized_pl > 0:
                drawdown = max(Decimal("0"), drawdown - item.realized_pl)

    for signal in ordered:
        settle_due_signals(signal.occurred_at)
        risk = _risk_result(
            applied_rules,
            daily_loss=daily_loss,
            drawdown=drawdown,
            open_risk=open_risk,
            open_positions=len(active),
        )
        _record_state(risk_states, signal.occurred_at, risk.state)
        if risk.state == RiskState.LOCKDOWN:
            prop_breach = True
            blocked.append((signal.id, risk.reason_codes[0]))
            continue

        reason: str | None = None
        dynamic_capacity = min(capacity - len(active), risk.capacity)
        if risk.state == RiskState.DEFENSIVE:
            dynamic_capacity = min(dynamic_capacity, max(0, 1 - len(active)))
        if dynamic_capacity <= 0:
            reason = (
                "RISK_STATE_CAPACITY"
                if risk.state == RiskState.DEFENSIVE and len(active) < capacity
                else "CAPACITY_EXHAUSTED"
            )
        elif len(active) >= capacity:
            reason = "CAPACITY_EXHAUSTED"
        elif signal.correlation_to_open > correlation_limit:
            reason = "CORRELATION_LIMIT"
        elif signal.common_exposure and any(
            item.common_exposure == signal.common_exposure for item in active.values()
        ):
            reason = "COMMON_FACTOR_EXPOSURE"
        elif open_risk + signal.risk > maximum_open_risk:
            reason = "OPEN_RISK_LIMIT"
        elif signal.risk > risk.remaining_daily_margin:
            reason = "DAILY_LOSS_MARGIN"
        elif signal.risk > risk.remaining_drawdown_margin:
            reason = "DRAWDOWN_MARGIN"
        if reason:
            blocked.append((signal.id, reason))
            continue
        selected.append(signal)
        active[signal.id] = signal
        open_risk += signal.risk
        peak_open_risk = max(peak_open_risk, open_risk)
        peak_open_positions = max(peak_open_positions, len(active))

    remaining_closes = sorted(
        item.closed_at for item in active.values() if item.closed_at is not None
    )
    for instant in remaining_closes:
        settle_due_signals(instant)
    final_risk = _risk_result(
        applied_rules,
        daily_loss=daily_loss,
        drawdown=drawdown,
        open_risk=open_risk,
        open_positions=len(active),
    )
    _record_state(risk_states, remaining_closes[-1] if remaining_closes else None, final_risk.state)
    prop_breach = prop_breach or final_risk.state == RiskState.LOCKDOWN
    return PortfolioSimulation(
        selected=tuple(selected),
        blocked=tuple(blocked),
        peak_open_risk=peak_open_risk,
        prop_breach=prop_breach,
        peak_open_positions=peak_open_positions,
        final_risk_state=final_risk.state,
        risk_states=tuple(risk_states),
        realized_daily_loss=daily_loss,
        realized_drawdown=drawdown,
    )


def _signal_order(signal: PortfolioSignal) -> tuple[bool, datetime | None, Decimal, str]:
    return (signal.occurred_at is None, signal.occurred_at, -signal.score, signal.id)


def _risk_result(
    rules: PortfolioRules,
    *,
    daily_loss: Decimal,
    drawdown: Decimal,
    open_risk: Decimal,
    open_positions: int,
) -> RiskResult:
    return calculate_risk(
        RiskInputs(
            equity=Decimal("0"),
            daily_loss=daily_loss,
            overall_drawdown=drawdown,
            open_risk=open_risk,
            prop_daily_limit=rules.prop_daily_loss_limit - rules.minimum_prop_buffer,
            internal_daily_limit=rules.internal_daily_loss_limit,
            prop_drawdown_limit=rules.prop_drawdown_limit - rules.minimum_prop_buffer,
            internal_drawdown_limit=rules.internal_drawdown_limit,
            open_positions=open_positions,
        )
    )


def _record_state(
    states: list[tuple[datetime | None, RiskState]],
    instant: datetime | None,
    state: RiskState,
) -> None:
    if not states or states[-1][1] != state:
        states.append((instant, state))
