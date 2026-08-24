from pathlib import Path


def test_trade_desk_exposes_evidence_and_human_controls() -> None:
    source = Path("apps/web/src/features/trading/TradeProposalPanel.tsx").read_text()
    assert all(
        label in source for label in ("Critic", "Take manually", "Wait", "Reject", "HARD_BLOCK")
    )
