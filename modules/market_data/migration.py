"""Legacy compatibility helpers; never infer type from a symbol alone."""

from __future__ import annotations

from typing import Any


def classify_legacy_record(record: dict[str, Any]) -> str:
    if record.get("instrument_type") and record.get("venue_instrument_id"):
        return "TYPED"
    return "LEGACY_UNTYPED"


def provable_typed_backfill(
    record: dict[str, Any], *, evidence: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Return a typed update only when an external authority proves every field."""
    if not evidence:
        return None
    required = (
        "asset_class",
        "instrument_type",
        "venue_instrument_id",
        "specification_version_id",
        "quantity_unit",
    )
    if any(not evidence.get(key) for key in required):
        return None
    return {**record, **{key: evidence[key] for key in required}, "classification": "TYPED"}


def require_typed_new_write(record: dict[str, Any]) -> None:
    if record.get("classification") == "LEGACY_UNTYPED":
        raise ValueError("legacy untyped records cannot be used for executable writes")
