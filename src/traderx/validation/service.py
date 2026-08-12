from __future__ import annotations

from dataclasses import dataclass

from traderx.validation.model import EvidenceState


@dataclass(frozen=True, slots=True)
class ValidationDecision:
    state: EvidenceState
    reason_codes: tuple[str, ...]


def aggregate_validation(
    *, out_of_sample_passed: bool, stability: str, portfolio_safe: bool, monte_carlo_passed: bool
) -> ValidationDecision:
    failures = []
    if not out_of_sample_passed:
        failures.append("OUT_OF_SAMPLE_FAILED")
    if stability != "STABLE":
        failures.append("PARAMETER_STABILITY_FAILED")
    if not portfolio_safe:
        failures.append("PORTFOLIO_SAFETY_FAILED")
    if not monte_carlo_passed:
        failures.append("TAIL_RISK_FAILED")
    return ValidationDecision(
        EvidenceState.PASS if not failures else EvidenceState.FAIL, tuple(failures)
    )
