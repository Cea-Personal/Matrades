from uuid import uuid4

from modules.journal.indexing import mark_indexed, queue_index
from modules.journal.models import JournalEntry, JournalEntryKind
from modules.notifications.service import NotificationService
from modules.performance.strategy_health import evaluate_health


def test_review_outputs_remain_ordered_and_deduplicated() -> None:
    entry = JournalEntry(owner_id=uuid4(), kind=JournalEntryKind.POST_TRADE, text="closed")
    queued = queue_index(entry)
    assert mark_indexed(queued).state == "INDEXED"
    item = NotificationService().confirmed_entry(
        owner_id=entry.owner_id,
        execution_command_id=uuid4(),
        fill_revision=1,
        channel="in_app",
        instrument="EURUSD",
        quantity="1 lot",
    )
    assert item.kind == "trade_entry_confirmed"
    assert evaluate_health({"expectancy": -1}, "v1").active_mutated is False
