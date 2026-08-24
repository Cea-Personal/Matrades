def simulate(losses: list[float], max_daily_loss: float, max_total_loss: float) -> dict[str, bool]:
    cumulative = 0.0
    for loss in losses:
        cumulative += max(0, loss)
        if loss > max_daily_loss or cumulative > max_total_loss:
            return {"passed": False}
    return {"passed": True}
