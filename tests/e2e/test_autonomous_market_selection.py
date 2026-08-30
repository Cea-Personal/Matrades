from pathlib import Path


def test_market_selection_ui_is_schedule_aware_and_safe() -> None:
    text = Path("apps/web/src/features/research/MarketSelection.tsx").read_text()
    assert all(value in text for value in ("Per-account research cycle", "Run time", "Schedule"))
    assert 'queryKey: ["research", "artifacts", selectedAccountId]' in text
    assert "/research/artifacts?account_id=${selectedAccountId}" in text
    assert "Cycle outcome · {selectedAccountName}" in text
    assert "Market research archive · {selectedAccountName}" in text
