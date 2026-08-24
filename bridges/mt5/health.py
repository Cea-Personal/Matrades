from __future__ import annotations

from datetime import timedelta

from packages.broker_sdk.schemas import BrokerHeartbeat
from packages.shared.domain_types import utc_now


def bridge_health(
    heartbeat: BrokerHeartbeat,
    max_age: timedelta = timedelta(seconds=10),
    max_clock_skew: timedelta = timedelta(seconds=3),
) -> dict[str, object]:
    age = utc_now() - heartbeat.observed_at
    return {
        "healthy": abs(age) <= max_age + max_clock_skew,
        "fresh": age <= max_age,
        "version": heartbeat.bridge_version,
        "capabilities": heartbeat.capabilities,
    }
