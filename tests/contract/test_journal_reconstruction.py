from uuid import uuid4

from modules.journal.service import JournalProjector
from packages.contracts.events import EventEnvelope


def test_journal_is_append_only_and_idempotent():
    owner, aggregate = uuid4(), uuid4()
    event = EventEnvelope(
        event_type="decision",
        owner_id=owner,
        aggregate_id=aggregate,
        aggregate_version=1,
        payload={},
    )
    journal = JournalProjector()
    journal.project(event)
    journal.project(event)
    assert journal.reconstruct(aggregate) == (event,)
