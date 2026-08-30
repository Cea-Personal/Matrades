from pathlib import Path


def test_strategy_lab_exposes_both_ai_origins_and_validation() -> None:
    text = Path("apps/web/src/features/strategies/StrategyBuilder.tsx").read_text()
    assert all(value in text for value in ("AI_GENERATED", "AI_ASSISTED", "Backtest", "Validation"))
