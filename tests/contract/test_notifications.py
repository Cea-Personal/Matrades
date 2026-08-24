from uuid import uuid4

from modules.notifications.service import NotificationService


def test_notifications_are_deduplicated():
    service = NotificationService()
    owner = uuid4()
    first = service.create(owner, "risk", "high", "Risk", "Review", "same")
    assert service.create(owner, "risk", "high", "Risk", "Review", "same").id == first.id
