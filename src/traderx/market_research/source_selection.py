from __future__ import annotations

from dataclasses import dataclass

from traderx.market_data.source_evidence import SourceEvidence, SourceRole


@dataclass(frozen=True, slots=True)
class SourceAttempt:
    provider: str
    attempt_number: int
    succeeded: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SourceTrailStep:
    role: SourceRole
    accepted: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceSelection:
    role: SourceRole | None
    evidence: tuple[SourceEvidence, ...]
    blocked: bool
    reason_codes: tuple[str, ...]
    trail: tuple[SourceTrailStep, ...]
    active_assignment_changed: bool = False


def select_market_source(
    *,
    specialist_attempts: list[SourceAttempt],
    specialist_evidence: list[SourceEvidence],
    mt5_evidence: list[SourceEvidence],
    cached_external_evidence: list[SourceEvidence],
    required_capabilities: set[str],
    twelve_data_evidence: list[SourceEvidence] | None = None,
) -> SourceSelection:
    """Select one complete evidence set without weakening gates or freshness.

    Specialist evidence is primary. Fallback is considered only once attempt three has
    completed; current MT5 evidence precedes cached specialist evidence. The selector
    never mutates an active market assignment.
    """

    trail: list[SourceTrailStep] = []
    specialist = _qualifying(specialist_evidence, required_capabilities)
    if specialist is not None:
        trail.append(SourceTrailStep(SourceRole.SPECIALIST_PRIMARY, True, ()))
        return SourceSelection(
            SourceRole.SPECIALIST_PRIMARY,
            specialist,
            False,
            (),
            tuple(trail),
        )

    specialist_reasons = _evidence_reasons(specialist_evidence, required_capabilities)
    if not _attempt_budget_exhausted(specialist_attempts):
        trail.append(
            SourceTrailStep(
                SourceRole.SPECIALIST_PRIMARY,
                False,
                ("SPECIALIST_RETRIES_NOT_EXHAUSTED", *specialist_reasons),
            )
        )
        return SourceSelection(
            None,
            (),
            True,
            ("SPECIALIST_RETRIES_NOT_EXHAUSTED",),
            tuple(trail),
        )

    trail.append(
        SourceTrailStep(
            SourceRole.SPECIALIST_PRIMARY,
            False,
            ("SPECIALIST_RETRIES_EXHAUSTED", *specialist_reasons),
        )
    )
    mt5 = _qualifying(mt5_evidence, required_capabilities)
    if mt5 is not None:
        trail.append(SourceTrailStep(SourceRole.FALLBACK_MT5, True, ()))
        return SourceSelection(SourceRole.FALLBACK_MT5, mt5, False, (), tuple(trail))
    trail.append(
        SourceTrailStep(
            SourceRole.FALLBACK_MT5,
            False,
            _evidence_reasons(mt5_evidence, required_capabilities),
        )
    )

    if twelve_data_evidence is not None:
        twelve = _qualifying(twelve_data_evidence, required_capabilities)
        if twelve is not None:
            trail.append(SourceTrailStep(SourceRole.FALLBACK_TWELVE_DATA, True, ()))
            return SourceSelection(SourceRole.FALLBACK_TWELVE_DATA, twelve, False, (), tuple(trail))
        trail.append(
            SourceTrailStep(
                SourceRole.FALLBACK_TWELVE_DATA,
                False,
                _evidence_reasons(twelve_data_evidence, required_capabilities),
            )
        )

    cached = _qualifying(cached_external_evidence, required_capabilities)
    if cached is not None:
        trail.append(SourceTrailStep(SourceRole.FALLBACK_CACHED_EXTERNAL, True, ()))
        return SourceSelection(
            SourceRole.FALLBACK_CACHED_EXTERNAL,
            cached,
            False,
            (),
            tuple(trail),
        )
    trail.append(
        SourceTrailStep(
            SourceRole.FALLBACK_CACHED_EXTERNAL,
            False,
            _evidence_reasons(cached_external_evidence, required_capabilities),
        )
    )
    return SourceSelection(
        None,
        (),
        True,
        ("NO_COMPLETE_FRESH_FALLBACK",),
        tuple(trail),
    )


def _attempt_budget_exhausted(attempts: list[SourceAttempt]) -> bool:
    return any(attempt.attempt_number >= 3 for attempt in attempts)


def _qualifying(
    evidence: list[SourceEvidence], required_capabilities: set[str]
) -> tuple[SourceEvidence, ...] | None:
    qualified = tuple(item for item in evidence if item.qualifies)
    available = {item.capability for item in qualified}
    return qualified if required_capabilities <= available else None


def _evidence_reasons(
    evidence: list[SourceEvidence], required_capabilities: set[str]
) -> tuple[str, ...]:
    if not evidence:
        return ("SOURCE_EVIDENCE_UNAVAILABLE",)
    qualified = {item.capability for item in evidence if item.qualifies}
    missing = sorted(required_capabilities - qualified)
    if missing:
        return tuple(f"CAPABILITY_NOT_QUALIFIED:{capability}" for capability in missing)
    return ("SOURCE_EVIDENCE_INCOMPLETE",)
