from modules.trading.broker_models import ManagementRecommendation, RecommendationAction


def interpret(trade_id, facts: dict[str, object]) -> ManagementRecommendation:
    if not facts.get("actionable"):
        return ManagementRecommendation(
            trade_id=trade_id,
            action=RecommendationAction.HOLD,
            reason=str(facts.get("reason", "deterministic checks block action")),
            requires_authorization=False,
        )
    return ManagementRecommendation(
        trade_id=trade_id,
        action=RecommendationAction.HOLD,
        reason="no deterministic trigger",
        requires_authorization=False,
    )
