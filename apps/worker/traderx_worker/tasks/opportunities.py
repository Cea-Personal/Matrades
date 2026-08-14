from __future__ import annotations

from celery import shared_task
from sqlalchemy import select

from traderx.opportunities.evaluator import evaluate_current_opportunities
from traderx.opportunities.model import Opportunity, OpportunityState
from traderx.opportunities.recommendation_model import Recommendation, RecommendationState
from traderx.shared.types import utc_now
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.opportunities.evaluate", bind=True, acks_late=True)
def evaluate_opportunities(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    with session_factory().begin() as database:
        items = evaluate_current_opportunities(database)
    return {"status": "COMPLETED", "evaluated": str(len(items))}


@shared_task(name="traderx.opportunities.expire", bind=True, acks_late=True)
def expire_recommendations(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    now = utc_now()
    expired = 0
    with session_factory().begin() as database:
        for opportunity in database.scalars(
            select(Opportunity).where(
                Opportunity.expires_at <= now, Opportunity.state == OpportunityState.CANDIDATE
            )
        ):
            opportunity.state = OpportunityState.EXPIRED
            expired += 1
        for recommendation in database.scalars(
            select(Recommendation).where(
                Recommendation.expires_at <= now, Recommendation.state == RecommendationState.ISSUED
            )
        ):
            recommendation.state = RecommendationState.EXPIRED
            expired += 1
    return {"status": "COMPLETED", "expired": str(expired)}
