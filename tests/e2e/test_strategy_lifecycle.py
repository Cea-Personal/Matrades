from pathlib import Path


def test_strategy_route_renders_real_validation_and_activation_controls():
    page = Path("apps/web/src/app/strategies/page.tsx").read_text()
    text = Path("apps/web/src/features/strategies/StrategyBuilder.tsx").read_text()
    assert "<StrategyBuilder" in page
    assert "<StrategyMonitoring" in text
    text += Path("apps/web/src/features/strategies/StrategyMonitoring.tsx").read_text()
    assert all(
        value in text
        for value in (
            "Accept proposal",
            "Reject proposal",
            "Create strategy version",
            "duplicate screening",
            "Run backtest",
            "Start paper session",
            "Activate strategy",
        )
    )


def test_strategy_ui_is_ai_only_and_has_generation_backtesting_and_archive():
    text = Path("apps/web/src/features/strategies/StrategyBuilder.tsx").read_text()
    assert all(
        value in text
        for value in (
            "AI Generated",
            "AI Assisted",
            "Generate strategy",
            "Accept proposal",
            "Create strategy version",
            "Run backtest",
            "Research archive",
            "Research basis",
            "Latest completed market research basis",
            "unseen holdout",
        )
    )
    assert "HUMAN_CREATED" not in text
    assert "IMPORTED" not in text
    assert "Validation JSON" not in text
