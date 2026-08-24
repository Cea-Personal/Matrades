def select_compatible(candidates: list[dict]) -> dict | None:
    eligible = [
        item
        for item in candidates
        if item.get("active") and item.get("compatible") and item.get("healthy")
    ]
    return max(eligible, key=lambda item: item.get("score", 0)) if eligible else None
