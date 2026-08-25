from pathlib import Path


def test_hil1_ui_has_evidence_replace_and_approve():
    text = Path("apps/web/src/features/research/MarketSelection.tsx").read_text()
    assert all(
        x in text
        for x in (
            "evidence",
            "Replace",
            "Approve universe",
            "DEGRADED",
            "Next scheduled cycle",
            "Run research now",
        )
    )
    assert "Candidate observations" not in text
    assert "Closing prices" not in text
