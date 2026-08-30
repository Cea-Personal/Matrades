from datetime import UTC, datetime


def lane_source_cut() -> dict[str, object]:
    return {
        "cut_id": "fixture-cut-1",
        "observed_at": datetime.now(UTC).isoformat(),
        "providers": ["fixture"],
    }


def twelve_lane_candidates() -> list[dict[str, object]]:
    return [{"asset_class": asset, "instrument_type": instrument, "instrument": "EURUSD"}
            for asset in ("FOREX", "METALS", "CRYPTOCURRENCY", "STOCKS")
            for instrument in ("SPOT", "CFD", "FUTURES")]
