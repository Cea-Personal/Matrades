from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class DeliveryUnavailable(RuntimeError):
    """The channel is not configured or could not confirm delivery."""


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    provider_reference: str
    confirmed: bool = True


class DeliveryProvider(Protocol):
    def deliver(self, notification_id: str, content: str) -> DeliveryReceipt: ...


class WebInboxProvider:
    def deliver(self, notification_id: str, content: str) -> DeliveryReceipt:
        return DeliveryReceipt(f"web:{notification_id}")


class EmailProvider:
    """Adapter around an approved email sender; credentials stay outside the payload."""

    def __init__(self, sender: Callable[[str, str], str]) -> None:
        self._sender = sender

    def deliver(self, notification_id: str, content: str) -> DeliveryReceipt:
        reference = self._sender(notification_id, content)
        if not reference:
            raise DeliveryUnavailable("email provider did not confirm delivery")
        return DeliveryReceipt(reference)


class TelegramProvider:
    """Adapter around an approved Telegram sender; no token is accepted per message."""

    def __init__(self, sender: Callable[[str, str], str]) -> None:
        self._sender = sender

    def deliver(self, notification_id: str, content: str) -> DeliveryReceipt:
        reference = self._sender(notification_id, content)
        if not reference:
            raise DeliveryUnavailable("Telegram provider did not confirm delivery")
        return DeliveryReceipt(reference)


class UnconfiguredExternalProvider:
    def __init__(self, channel: str) -> None:
        self._channel = channel

    def deliver(self, notification_id: str, content: str) -> DeliveryReceipt:
        raise DeliveryUnavailable(f"{self._channel} delivery is not configured")
