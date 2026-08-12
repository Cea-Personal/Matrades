from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    event_id: str
    sequence: int
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    accepted: tuple[ProviderEvent, ...]
    reason_codes: tuple[str, ...]


def reconcile(events: list[ProviderEvent], *, last_sequence: int) -> ReconciliationResult:
    deduplicated: dict[str, ProviderEvent] = {event.event_id: event for event in events}
    ordered = tuple(sorted(deduplicated.values(), key=lambda event: event.sequence))
    reasons = []
    if ordered and ordered[0].sequence > last_sequence + 1:
        reasons.append("PROVIDER_SEQUENCE_GAP")
    if any(event.sequence <= last_sequence for event in ordered):
        reasons.append("OUT_OF_ORDER_OR_DUPLICATE")
    return ReconciliationResult(
        tuple(event for event in ordered if event.sequence > last_sequence), tuple(reasons)
    )
