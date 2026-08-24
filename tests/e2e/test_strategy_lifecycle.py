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
