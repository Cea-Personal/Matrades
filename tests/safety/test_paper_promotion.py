from decimal import Decimal

from traderx.paper.evidence import assess_paper_evidence


def test_duration_alone_cannot_paper_promote_a_strategy() -> None:
    result = assess_paper_evidence(
        trades=1,
        duration_days=30,
        historical_expectancy=Decimal("1"),
        paper_expectancy=Decimal("1"),
        maximum_divergence=Decimal(".1"),
        validation_passed=True,
    )
    assert not result.eligible
    assert "INSUFFICIENT_PAPER_TRADES" in result.reason_codes
