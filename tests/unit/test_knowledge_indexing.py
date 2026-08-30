from uuid import uuid4

from modules.journal.indexing import mark_indexed, queue_index
from modules.journal.models import JournalEntry, JournalEntryKind


def test_journal_index_work_is_generation_tagged():
    entry = JournalEntry(owner_id=uuid4(), kind=JournalEntryKind.EXECUTION, text="filled")
    queued = queue_index(entry, generation=3)
    indexed = mark_indexed(queued)
    assert queued.state == "QUEUED"
    assert indexed.state == "INDEXED"
    assert indexed.generation == 3
