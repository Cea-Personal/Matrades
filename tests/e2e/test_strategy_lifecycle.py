from pathlib import Path


def test_strategy_ui_has_decisions_similarity_and_promotion():
    text = "".join(
        Path(x).read_text()
        for x in (
            "apps/web/src/features/strategies/StrategyBuilder.tsx",
            "apps/web/src/features/strategies/SimilarityReview.tsx",
            "apps/web/src/features/strategies/ValidationResults.tsx",
        )
    )
    assert all(x in text for x in ("Accept", "Edit", "Reject", "Similarity", "Promote"))


def test_strategy_ui_is_ai_only_and_has_generation_backtesting_and_archive():
    text = Path("apps/web/src/features/strategies/StrategyBuilder.tsx").read_text()
    assert all(
        value in text
        for value in (
            "AI Generated",
            "AI Assisted",
            "Generate strategy",
            "Approve strategy",
            "Run backtest",
            "Research archive",
            "Research basis",
            "approved market selection",
            "unseen holdout",
        )
    )
    assert "HUMAN_CREATED" not in text
    assert "IMPORTED" not in text
    assert "Validation JSON" not in text
