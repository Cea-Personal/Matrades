from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HealthAssessment:
    state: str
    suspend_recommended: bool


def assess_live_health(
    *, current_metric: Decimal, expected_lower_bound: Decimal
) -> HealthAssessment:
    if current_metric < expected_lower_bound:
        return HealthAssessment("WATCH", True)
    return HealthAssessment("HEALTHY", False)
