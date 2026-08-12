from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeliveryPlan:
    channels: tuple[str, ...]
    persist_web_inbox: bool


def route(*, severity: str, enabled_channels: set[str]) -> DeliveryPlan:
    channels = tuple(sorted(enabled_channels))
    return DeliveryPlan(channels, severity in {"CRITICAL", "HIGH"})


def retryable(attempt: int, maximum: int = 3) -> bool:
    return attempt < maximum
