def context_features(
    *, macro: float, event_risk: float, sentiment: float, positioning: float, correlation: float
) -> dict[str, float]:
    values = {
        "macro": macro,
        "event_risk": event_risk,
        "sentiment": sentiment,
        "positioning": positioning,
        "correlation": correlation,
    }
    if (
        any(not -1 <= value <= 1 for key, value in values.items() if key != "event_risk")
        or not 0 <= event_risk <= 1
    ):
        raise ValueError("normalized feature outside its bounds")
    return values
