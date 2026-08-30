from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from modules.journal.models import JournalEntry, JournalEntryKind
from packages.contracts.events import EventEnvelope


class JournalProjector:
    def __init__(self):
        self.events = defaultdict(list)

    def project(self, event: EventEnvelope) -> None:
        if any(x.event_id == event.event_id for x in self.events[event.aggregate_id]):
            return
        self.events[event.aggregate_id].append(event)
        self.events[event.aggregate_id].sort(key=lambda x: (x.aggregate_version, x.recorded_at))

    def reconstruct(self, aggregate_id: UUID) -> tuple[EventEnvelope, ...]:
        return tuple(self.events[aggregate_id])

    def live_entry(
        self,
        event: EventEnvelope,
        *,
        kind: JournalEntryKind = JournalEntryKind.SYSTEM,
        text: str | None = None,
        knowledge_source_id=None,
    ) -> JournalEntry:
        """Project an execution/position event into a journal entry for knowledge indexing."""
        self.project(event)
        return JournalEntry(
            owner_id=event.owner_id,
            trade_id=event.aggregate_id,
            kind=kind,
            text=text or event.event_type,
            facts={"event_type": event.event_type, **event.payload},
            source_event_id=event.event_id,
            knowledge_source_id=knowledge_source_id,
            recorded_at=event.recorded_at,
        )

    def terminal_summary(self, aggregate_id, *, text: str | None = None) -> JournalEntry:
        """Build a deterministic post-trade summary from the immutable event stream."""
        events = self.reconstruct(aggregate_id)
        if not events:
            raise ValueError("cannot summarize a trade without journal events")
        terminal = events[-1]
        return JournalEntry(
            owner_id=terminal.owner_id,
            trade_id=aggregate_id,
            kind=JournalEntryKind.POST_TRADE,
            text=text or f"Terminal trade outcome: {terminal.event_type}",
            facts={
                "terminal_event": terminal.event_type,
                "event_count": len(events),
                "event_ids": [str(item.event_id) for item in events],
                "terminal_payload": terminal.payload,
            },
            source_event_id=terminal.event_id,
            recorded_at=terminal.recorded_at,
        )
