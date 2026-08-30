from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from modules.journal.models import JournalEntry


@dataclass(frozen=True)
class JournalIndexWorkItem:
    id: UUID
    owner_id: UUID
    journal_entry_id: UUID
    generation: int = 1
    state: str = "QUEUED"


def queue_index(entry: JournalEntry, *, generation: int = 1) -> JournalIndexWorkItem:
    return JournalIndexWorkItem(
        id=uuid4(), owner_id=entry.owner_id, journal_entry_id=entry.id, generation=generation
    )


def mark_indexed(item: JournalIndexWorkItem) -> JournalIndexWorkItem:
    return JournalIndexWorkItem(
        id=item.id,
        owner_id=item.owner_id,
        journal_entry_id=item.journal_entry_id,
        generation=item.generation,
        state="INDEXED",
    )
