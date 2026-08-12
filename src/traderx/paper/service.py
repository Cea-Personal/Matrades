from __future__ import annotations

from dataclasses import dataclass

from traderx.paper.evidence import PaperEligibility


@dataclass(frozen=True, slots=True)
class PaperTerminalDisposition:
    state: str
    reason_codes: tuple[str, ...]


def terminal_disposition(evidence: PaperEligibility) -> PaperTerminalDisposition:
    return PaperTerminalDisposition(evidence.disposition, evidence.reason_codes)
