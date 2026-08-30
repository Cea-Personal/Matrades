from uuid import uuid4

from modules.journal.models import JournalEntryKind
from modules.journal.service import JournalProjector
from packages.contracts.events import EventEnvelope


def test_terminal_journal_summary_is_reconstructable_and_idempotent() -> None:
    aggregate_id = uuid4()
    event = EventEnvelope(
        event_type="trade.closed",
        owner_id=uuid4(),
        aggregate_id=aggregate_id,
        aggregate_version=1,
        payload={"pnl": "12.50"},
    )
    projector = JournalProjector()
    entry = projector.live_entry(event, kind=JournalEntryKind.EXECUTION)
    projector.project(event)
    summary = projector.terminal_summary(aggregate_id)
    assert entry.source_event_id == event.event_id
    assert summary.kind is JournalEntryKind.POST_TRADE
    assert summary.facts["event_count"] == 1
