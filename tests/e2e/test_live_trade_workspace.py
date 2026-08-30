from pathlib import Path


def test_active_chart_is_read_only() -> None:
    text = Path("apps/web/src/features/trading/ActiveTradeChart.tsx").read_text()
    assert "Read-only" in text
    assert "command" not in text.lower().replace("commands", "")
