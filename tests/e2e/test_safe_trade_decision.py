from pathlib import Path


def test_trade_desk_exposes_autonomous_trade_plan_and_no_hil_controls() -> None:
    source = Path("apps/web/src/features/trading/TradeManagement.tsx").read_text()
    assert all(
        label in source
        for label in (
            "Autonomous trade operations",
            "Trade Plan lifecycle",
            "Stop",
            "Risk",
            "kill switches",
        )
    )
    assert all(label not in source for label in ("Take manually", "Approve", "Reject"))
