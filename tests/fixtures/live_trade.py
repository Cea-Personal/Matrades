from uuid import uuid4

from modules.journal.models import JournalEntry, JournalEntryKind
from modules.notifications.service import NotificationService


def journal_entry() -> JournalEntry:
    return JournalEntry(owner_id=uuid4(), kind=JournalEntryKind.EXECUTION, text="fixture execution")


def notification_service() -> NotificationService:
    return NotificationService()
