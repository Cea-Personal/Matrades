from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.journal.model import JournalEntry
from traderx.shared.types import utc_now
from traderx.strategies.health_model import StrategyHealthObservation, StrategySuspension
from traderx.strategies.model import StrategyLifecycle, StrategyVersion
from traderx.validation.model import EvidenceState, ValidationRun


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


def observe_live_strategy_health(
    database: Session, *, observed_at: datetime | None = None, window: int = 30
) -> list[StrategyHealthObservation]:
    """Append rolling health evidence and conservatively suspend repeated adverse results."""

    now = observed_at or utc_now()
    versions = database.scalars(
        select(StrategyVersion).where(
            StrategyVersion.lifecycle.in_(
                [
                    StrategyLifecycle.LIVE_APPROVED,
                    StrategyLifecycle.LIVE,
                    StrategyLifecycle.WATCH,
                ]
            )
        )
    ).all()
    journal = database.scalars(select(JournalEntry).order_by(JournalEntry.closed_at.desc())).all()
    observations: list[StrategyHealthObservation] = []
    for version in versions:
        relevant = [
            entry
            for entry in journal
            if str(entry.evidence.get("strategy_version_id")) == str(version.id)
        ][:window]
        validation = database.scalar(
            select(ValidationRun)
            .where(
                ValidationRun.strategy_version_id == version.id,
                ValidationRun.state == EvidenceState.PASS,
            )
            .order_by(ValidationRun.created_at.desc())
            .limit(1)
        )
        expected_lower = _expected_lower_bound(validation)
        current = (
            sum((Decimal(str(entry.r_multiple or 0)) for entry in relevant), Decimal("0"))
            / Decimal(len(relevant))
            if relevant
            else None
        )
        prior = database.scalar(
            select(StrategyHealthObservation)
            .where(StrategyHealthObservation.strategy_version_id == version.id)
            .order_by(StrategyHealthObservation.observed_at.desc())
            .limit(1)
        )
        if current is None or expected_lower is None:
            state = "INSUFFICIENT_EVIDENCE"
            suspend_recommended = False
        else:
            assessment = assess_live_health(
                current_metric=current, expected_lower_bound=expected_lower
            )
            state = assessment.state
            suspend_recommended = assessment.suspend_recommended
        observation = StrategyHealthObservation(
            strategy_version_id=version.id,
            state=state,
            evidence={
                "sample_size": len(relevant),
                "window": window,
                "current_average_r": str(current) if current is not None else None,
                "expected_lower_bound_r": (
                    str(expected_lower) if expected_lower is not None else None
                ),
                "suspend_recommended": suspend_recommended,
            },
            observed_at=now,
        )
        database.add(observation)
        observations.append(observation)
        if suspend_recommended:
            repeated = prior is not None and prior.state == "WATCH"
            version.lifecycle = StrategyLifecycle.SUSPENDED if repeated else StrategyLifecycle.WATCH
            if repeated:
                database.add(
                    StrategySuspension(
                        strategy_version_id=version.id,
                        state="ENFORCED",
                        reason="Rolling live R fell below the validated lower bound twice.",
                        created_at=now,
                    )
                )
        elif state == "HEALTHY" and version.lifecycle == StrategyLifecycle.WATCH:
            version.lifecycle = StrategyLifecycle.LIVE_APPROVED
    database.flush()
    return observations


def _expected_lower_bound(validation: ValidationRun | None) -> Decimal | None:
    if validation is None:
        return None
    for key in ("expected_lower_bound_r", "minimum_expected_r"):
        value = validation.evidence.get(key)
        if value is not None:
            return Decimal(str(value))
    return None
