from pathlib import Path


def test_management_ui_is_an_autonomous_operations_monitor():
    text = Path("apps/web/src/features/trading/TradeManagement.tsx").read_text()
    assert all(
        x in text for x in ("Autonomous trade operations", "Trade Plans", "operational monitor")
    )
    assert "AWAITING_MANUAL_ENTRY" not in text
    assert "Take manually" not in text
