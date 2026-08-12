from decimal import Decimal

from traderx.journal.projector import project_trade


def test_journal_projects_exact_financial_and_r_outcomes() -> None:
    result = project_trade(
        entry=Decimal("100"),
        exit=Decimal("110"),
        units=Decimal("2"),
        direction="LONG",
        costs=Decimal("1"),
        initial_risk=Decimal("10"),
    )
    assert result.net_pnl == Decimal("19")
    assert result.r_multiple == Decimal("1.9")
