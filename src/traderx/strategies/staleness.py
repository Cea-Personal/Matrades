from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class EvidenceFreshness(StrEnum):
    CURRENT = "CURRENT"
    REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"
    STALE = "STALE"
    LEGACY = "LEGACY"


@dataclass(frozen=True, slots=True)
class RevalidationPlan:
    freshness: EvidenceFreshness
    steps: tuple[str, ...]


def classify_evidence(
    *,
    validated_at: datetime,
    now: datetime,
    data_gap: bool,
    max_age: timedelta = timedelta(days=90),
) -> RevalidationPlan:
    age = now - validated_at
    if age < timedelta(0):
        return RevalidationPlan(
            EvidenceFreshness.STALE,
            ("REFRESH_DATA", "FULL_VALIDATION", "PAPER", "HUMAN_APPROVAL"),
        )
    if age >= max_age * 4:
        return RevalidationPlan(
            EvidenceFreshness.LEGACY, ("FULL_RESEARCH", "BACKTEST", "PAPER", "HUMAN_APPROVAL")
        )
    if age >= max_age * 2:
        return RevalidationPlan(
            EvidenceFreshness.STALE,
            ("REFRESH_DATA", "FULL_VALIDATION", "PAPER", "HUMAN_APPROVAL"),
        )
    if data_gap or age >= max_age:
        return RevalidationPlan(
            EvidenceFreshness.REVALIDATION_REQUIRED,
            (
                "REFRESH_MISSING_INTERVALS" if data_gap else "REFRESH_DATA",
                "SELECTIVE_VALIDATION",
                "HUMAN_APPROVAL",
            ),
        )
    return RevalidationPlan(EvidenceFreshness.CURRENT, ())
