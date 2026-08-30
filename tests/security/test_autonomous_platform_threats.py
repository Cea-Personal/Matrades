from pathlib import Path


def test_release_boundaries_are_present() -> None:
    chart = Path("apps/web/src/features/trading/ActiveTradeChart.tsx").read_text()
    agent = Path("apps/api/app/routes/automation.py").read_text()
    assert "Read-only" in chart
    assert "execution" in agent.lower() and "permissions" in agent.lower()
