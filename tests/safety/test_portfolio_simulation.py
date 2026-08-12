from decimal import Decimal

from traderx.validation.portfolio import PortfolioSignal, select_signals


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
