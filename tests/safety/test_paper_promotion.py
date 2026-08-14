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


def test_combined_evidence_and_divergence_are_required_but_never_auto_approve() -> None:
    divergent = assess_paper_evidence(
        trades=30,
        duration_days=30,
        historical_expectancy=Decimal("1"),
        paper_expectancy=Decimal("0.2"),
        maximum_divergence=Decimal("0.25"),
        validation_passed=True,
    )
    assert divergent.disposition == "REVIEW_REQUIRED"
    assert "PAPER_HISTORICAL_DIVERGENCE" in divergent.reason_codes
    passing = assess_paper_evidence(
        trades=30,
        duration_days=30,
        historical_expectancy=Decimal("1"),
        paper_expectancy=Decimal("0.9"),
        maximum_divergence=Decimal("0.25"),
        validation_passed=True,
    )
    assert passing.eligible is True
    assert passing.disposition == "AWAITING_APPROVAL"
    assert passing.disposition != "LIVE_APPROVED"
