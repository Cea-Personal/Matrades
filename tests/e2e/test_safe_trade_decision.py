from pathlib import Path


def test_trade_desk_exposes_autonomous_trade_plan_and_no_hil_controls() -> None:
    source = Path("apps/web/src/features/trading/TradeProposalPanel.tsx").read_text()
    assert all(label in source for label in ("Autonomous Trade Plan", "Entry", "Stop", "Size"))
    assert all(label not in source for label in ("Take manually", "Approve", "Reject"))
