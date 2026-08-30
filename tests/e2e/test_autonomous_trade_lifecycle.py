from pathlib import Path


def test_operations_surface_is_autonomous_and_not_an_approval_queue() -> None:
    text = Path("apps/web/src/features/trading/TradeManagement.tsx").read_text()
    assert "AUTONOMOUS" in text
    assert "approval queue" in text
    assert "human_approval_required" not in text
