from __future__ import annotations

from uuid import UUID

from modules.performance.models import Notification


class NotificationService:
    def __init__(self):
        self.items = {}
        self.preferences = {}

    def create(
        self, owner_id: UUID, kind: str, urgency: str, title: str, body: str, dedupe_key: str
    ) -> Notification:
        key = (owner_id, dedupe_key)
        if key in self.items:
            return self.items[key]
        item = Notification(
            owner_id=owner_id,
            kind=kind,
            urgency=urgency,
            title=title,
            body=body,
            dedupe_key=dedupe_key,
        )
        self.items[key] = item
        return item

    def mark(self, item: Notification, state: str) -> Notification:
        updated = item.model_copy(update={"state": state})
        self.items[(item.owner_id, item.dedupe_key)] = updated
        return updated
