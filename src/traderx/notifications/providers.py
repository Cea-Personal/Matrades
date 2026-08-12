from __future__ import annotations

from typing import Protocol


class DeliveryProvider(Protocol):
    def deliver(self, notification_id: str, content: str) -> str: ...


class WebInboxProvider:
    def deliver(self, notification_id: str, content: str) -> str:
        return f"web:{notification_id}"
