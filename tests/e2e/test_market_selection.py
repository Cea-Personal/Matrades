from pathlib import Path


def test_market_research_ui_is_schedule_driven_and_autonomous():
    text = Path("apps/web/src/features/research/MarketSelection.tsx").read_text()
    assert all(
        x in text
        for x in (
            "Evidence",
            "DEGRADED",
            "Next scheduled cycle",
            "Run configured matrix now",
            "scheduled research cycle",
        )
    )
    assert "Approve universe" not in text
    assert "Replace candidates" not in text
    assert "Human-in-the-loop" not in text


def test_typed_matrix_is_summary_only_and_extras_owns_decision_evidence() -> None:
    matrix = Path("apps/web/src/features/research/MarketSelection.tsx").read_text()
    extras = Path("apps/web/src/features/extras/Extras.tsx").read_text()
    assert "View detailed evidence in Extras" in matrix
    assert "Agent decision trace" not in matrix
    assert "Provider / runtime detail" not in matrix
    assert "Research decision evidence" in extras
    assert "Agent decision trace" in extras
    assert "Provider / runtime detail" in extras
