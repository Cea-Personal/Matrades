from modules.strategies.models import StrategyDraft, Suggestion


def suggest(draft: StrategyDraft) -> list[Suggestion]:
    suggestions = []
    if draft.specification is None:
        suggestions.append(
            Suggestion(
                draft_id=draft.id,
                path="specification",
                proposed_value={},
                explanation="Complete deterministic rules before validation.",
            )
        )
    return suggestions
