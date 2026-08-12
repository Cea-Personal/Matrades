from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchHypothesis:
    text: str
    evidence_links: tuple[str, ...]
    strategy_version_id: str | None
    state: str = "PROPOSED"


def propose(
    *, text: str, evidence_links: list[str], strategy_version_id: str | None
) -> ResearchHypothesis:
    if not text.strip() or not evidence_links:
        raise ValueError("a research hypothesis needs text and linked evidence")
    return ResearchHypothesis(text, tuple(evidence_links), strategy_version_id)
