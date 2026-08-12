from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from traderx.integrations.crypto import redact


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    name: str
    correlation_id: str | None
    attributes: dict[str, object]


def emit(event: TelemetryEvent) -> None:
    """Structured, redacted seam for logs, traces, metrics, and alert exporters."""
    logging.getLogger("traderx").info(
        json.dumps(
            {
                "event": event.name,
                "correlation_id": event.correlation_id,
                "attributes": redact(event.attributes),
            },
            default=str,
        )
    )
