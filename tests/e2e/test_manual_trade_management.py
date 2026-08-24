from pathlib import Path


def test_management_ui_states_and_manual_language():
    text = Path("apps/web/src/features/trading/TradeManagement.tsx").read_text()
    assert all(x in text for x in ("AWAITING_MANUAL_ENTRY", "AMBIGUOUS", "ACTIVE", "manually"))
