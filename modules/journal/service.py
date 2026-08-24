from __future__ import annotations

from collections import defaultdict

from packages.contracts.events import EventEnvelope


class JournalProjector:
    def __init__(self):
        self.events = defaultdict(list)

    def project(self, event: EventEnvelope) -> None:
        if any(x.event_id == event.event_id for x in self.events[event.aggregate_id]):
            return
        self.events[event.aggregate_id].append(event)
        self.events[event.aggregate_id].sort(key=lambda x: (x.aggregate_version, x.recorded_at))

    def reconstruct(self, aggregate_id):
        return tuple(self.events[aggregate_id])
