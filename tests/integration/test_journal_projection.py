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


def test_recommended_discretionary_and_paper_math_share_exact_long_short_rules() -> None:
    short = project_trade(
        entry=Decimal("110"),
        exit=Decimal("100"),
        units=Decimal("2"),
        direction="SHORT",
        costs=Decimal("1.5"),
        initial_risk=Decimal("10"),
    )
    assert short.gross_pnl == Decimal("20")
    assert short.net_pnl == Decimal("18.5")
    assert short.r_multiple == Decimal("1.85")
    unverified_risk = project_trade(
        entry=Decimal("100"),
        exit=Decimal("101"),
        units=Decimal("1"),
        direction="LONG",
        costs=Decimal("0"),
        initial_risk=Decimal("0"),
    )
    assert unverified_risk.r_multiple is None
