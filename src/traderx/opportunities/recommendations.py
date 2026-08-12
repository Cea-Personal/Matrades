from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from traderx.risk.manager import ManagedDecision
from traderx.shared.types import RiskDecisionKind


@dataclass(frozen=True, slots=True)
class RecommendationDraft:
    entry: Decimal
    stop: Decimal
    volume: Decimal
    expires_at: datetime
    state: str = "ISSUED"


def issue(
    decision: ManagedDecision, draft: RecommendationDraft, *, now: datetime
) -> RecommendationDraft | None:
    if (
        decision.decision == RiskDecisionKind.BLOCKED
        or draft.volume <= 0
        or now >= draft.expires_at
    ):
        return None
    return draft


def withdraw(draft: RecommendationDraft) -> RecommendationDraft:
    return replace(draft, state="WITHDRAWN")
