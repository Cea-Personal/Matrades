from uuid import uuid4

from modules.journal.models import JournalEntryKind
from modules.journal.service import JournalProjector
from packages.contracts.events import EventEnvelope


def test_live_event_is_projected_as_knowledge_ready_journal_entry():
    event = EventEnvelope(
        owner_id=uuid4(), aggregate_id=uuid4(), aggregate_version=1,
        event_type="execution.command.acknowledged", payload={"broker_order_id": "42"},
    )
    entry = JournalProjector().live_entry(event, kind=JournalEntryKind.EXECUTION)

    assert entry.kind == JournalEntryKind.EXECUTION
    assert entry.source_event_id == event.event_id
    assert entry.facts["broker_order_id"] == "42"
