from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.shared.types import RiskState
from traderx.validation.portfolio import (
    PortfolioRules,
    PortfolioSignal,
    select_signals,
    simulate_shared_account,
)


def test_portfolio_simulation_honors_maximum_two_and_correlation_limit() -> None:
    selected = select_signals(
        [
            PortfolioSignal("a", Decimal("3"), Decimal("1"), Decimal(".1")),
            PortfolioSignal("b", Decimal("2"), Decimal("1"), Decimal(".2")),
            PortfolioSignal("c", Decimal("10"), Decimal("1"), Decimal(".9")),
        ],
        capacity=2,
        correlation_limit=Decimal(".5"),
    )
    assert [item.id for item in selected] == ["a", "b"]


def test_shared_account_blocks_common_factor_and_open_risk_breaches() -> None:
    simulation = simulate_shared_account(
        [
            PortfolioSignal("eurusd", Decimal("3"), Decimal("0.01"), Decimal("0.1"), "USD"),
            PortfolioSignal("xauusd", Decimal("2"), Decimal("0.01"), Decimal("0.1"), "USD"),
            PortfolioSignal("btcusd", Decimal("1"), Decimal("0.02"), Decimal("0.1"), "CRYPTO"),
        ],
        capacity=2,
        correlation_limit=Decimal("0.5"),
        maximum_open_risk=Decimal("0.02"),
    )
    assert [item.id for item in simulation.selected] == ["eurusd"]
    assert dict(simulation.blocked) == {
        "xauusd": "COMMON_FACTOR_EXPOSURE",
        "btcusd": "OPEN_RISK_LIMIT",
    }
    assert simulation.prop_breach is False


def test_shared_account_replays_closures_and_competes_signals_chronologically() -> None:
    first = datetime(2026, 1, 5, 9, tzinfo=UTC)
    simulation = simulate_shared_account(
        [
            PortfolioSignal(
                "lower-score",
                Decimal("2"),
                Decimal("0.01"),
                Decimal("0.1"),
                occurred_at=first,
            ),
            PortfolioSignal(
                "higher-score",
                Decimal("3"),
                Decimal("0.01"),
                Decimal("0.1"),
                occurred_at=first,
                closed_at=first + timedelta(hours=1),
                realized_pl=Decimal("25"),
            ),
            PortfolioSignal(
                "after-close",
                Decimal("1"),
                Decimal("0.01"),
                Decimal("0.1"),
                occurred_at=first + timedelta(hours=1),
            ),
        ],
        capacity=1,
        correlation_limit=Decimal("0.5"),
        maximum_open_risk=Decimal("0.02"),
    )

    assert [item.id for item in simulation.selected] == ["higher-score", "after-close"]
    assert dict(simulation.blocked) == {"lower-score": "CAPACITY_EXHAUSTED"}
    assert simulation.peak_open_positions == 1


def test_shared_account_applies_prop_buffer_and_dynamic_defensive_capacity() -> None:
    instant = datetime(2026, 1, 5, 9, tzinfo=UTC)
    rules = PortfolioRules(
        prop_daily_loss_limit=Decimal("100"),
        internal_daily_loss_limit=Decimal("100"),
        prop_drawdown_limit=Decimal("200"),
        internal_drawdown_limit=Decimal("200"),
        minimum_prop_buffer=Decimal("10"),
    )
    defensive = simulate_shared_account(
        [
            PortfolioSignal("winner", Decimal("3"), Decimal("5"), Decimal("0.1"), occurred_at=instant),
            PortfolioSignal("runner-up", Decimal("2"), Decimal("5"), Decimal("0.1"), occurred_at=instant),
        ],
        capacity=2,
        correlation_limit=Decimal("0.5"),
        maximum_open_risk=Decimal("20"),
        rules=rules,
        initial_daily_loss=Decimal("70"),
        initial_drawdown=Decimal("70"),
    )

    assert defensive.final_risk_state == RiskState.DEFENSIVE
    assert [item.id for item in defensive.selected] == ["winner"]
    assert dict(defensive.blocked) == {"runner-up": "RISK_STATE_CAPACITY"}


def test_realized_loss_trips_prop_rule_before_later_signal() -> None:
    first = datetime(2026, 1, 5, 9, tzinfo=UTC)
    rules = PortfolioRules(
        prop_daily_loss_limit=Decimal("100"),
        internal_daily_loss_limit=Decimal("100"),
        prop_drawdown_limit=Decimal("200"),
        internal_drawdown_limit=Decimal("200"),
    )
    simulation = simulate_shared_account(
        [
            PortfolioSignal(
                "loss",
                Decimal("3"),
                Decimal("10"),
                Decimal("0.1"),
                occurred_at=first,
                closed_at=first + timedelta(hours=1),
                realized_pl=Decimal("-100"),
            ),
            PortfolioSignal(
                "too-late",
                Decimal("2"),
                Decimal("10"),
                Decimal("0.1"),
                occurred_at=first + timedelta(hours=2),
            ),
        ],
        capacity=2,
        correlation_limit=Decimal("0.5"),
        maximum_open_risk=Decimal("20"),
        rules=rules,
    )

    assert simulation.prop_breach is True
    assert simulation.final_risk_state == RiskState.LOCKDOWN
    assert dict(simulation.blocked) == {"too-late": "DAILY_LOSS_LIMIT_REACHED"}
