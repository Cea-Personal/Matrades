def walk_forward(values: list[float], folds: int = 3) -> dict[str, float]:
    if len(values) < folds * 2:
        raise ValueError("insufficient chronological samples")
    split = len(values) // folds
    scores = [sum(values[i * split : (i + 1) * split]) / split for i in range(folds)]
    return {"mean": sum(scores) / len(scores), "worst": min(scores)}
