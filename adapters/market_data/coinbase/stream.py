from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass
class SequenceGuard:
    stale_after_seconds: float = 10
    last_sequence: int | None = None
    last_received: float | None = None
    needs_resync: bool = False

    def accept(self, sequence: int) -> bool:
        if self.last_sequence is not None and sequence != self.last_sequence + 1:
            self.needs_resync = True
            return False
        self.last_sequence, self.last_received, self.needs_resync = sequence, monotonic(), False
        return True

    @property
    def stale(self) -> bool:
        return (
            self.last_received is None
            or monotonic() - self.last_received > self.stale_after_seconds
        )

    def reconnect(self, snapshot_sequence: int) -> None:
        self.last_sequence, self.last_received, self.needs_resync = (
            snapshot_sequence,
            monotonic(),
            False,
        )
