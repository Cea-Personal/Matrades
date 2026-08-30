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
