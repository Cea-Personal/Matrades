from __future__ import annotations

from datetime import datetime

from modules.analysis.models import EconomicEvent


def normalize_event(payload: dict, source: str) -> EconomicEvent:
    return EconomicEvent(
        name=str(payload["name"]),
        currency=str(payload["currency"]).upper(),
        impact=str(payload.get("impact", "UNKNOWN")).upper(),
        scheduled_at=datetime.fromisoformat(str(payload["scheduled_at"])),
        source=source,
    )
