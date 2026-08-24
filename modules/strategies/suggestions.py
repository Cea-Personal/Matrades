from modules.strategies.models import StrategyDraft, Suggestion, SuggestionDecision


def decide(
    draft: StrategyDraft,
    suggestion: Suggestion,
    decision: SuggestionDecision,
    edited_value: object | None = None,
) -> tuple[StrategyDraft, Suggestion]:
    if suggestion.draft_id != draft.id or suggestion.decision != SuggestionDecision.PENDING:
        raise ValueError("suggestion cannot be decided")
    if decision == SuggestionDecision.EDIT and edited_value is None:
        raise ValueError("edited value required")
    return draft.model_copy(update={"revision": draft.revision + 1}), suggestion.model_copy(
        update={
            "decision": decision,
            "proposed_value": edited_value
            if decision == SuggestionDecision.EDIT
            else suggestion.proposed_value,
        }
    )
