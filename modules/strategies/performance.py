"""Account-pinned library eligibility and recorded forward-performance health."""

from modules.backtesting.robustness import return_statistics

FORMAL_GATES = (
    "backtest",
    "out_of_sample",
    "walk_forward",
    "stress",
    "policy",
    "parameter_sensitivity",
    "cost_stress",
)
MIN_REGIME_TRADES = 10


def rolling_health(trades: list[dict]) -> dict:
    # Never substitute an aggregate manual PnL or current unrealized position.
    values = [float(t["r"]) for t in trades if t.get("r") is not None]
    windows = {}
    for size in (30, 60, 100):
        sample = values[-size:]
        stats = return_statistics(sample)
        windows[str(size)] = {**stats, "complete": len(sample) == size}
    degraded = any(w["complete"] and w["average_r"] <= 0 for w in windows.values())
    return {
        "status": "DEGRADED" if degraded else "HEALTHY" if len(values) >= 30 else "WARMUP",
        "suspend": degraded,
        "windows": windows,
        "reason": "A complete rolling window has non-positive expectancy after costs"
        if degraded
        else "At least 30 recorded closed trades required"
        if len(values) < 30
        else "Complete rolling windows retain positive expectancy",
        "basis": "RECORDED_FORWARD_SIMULATION_NOT_BROKER_FILLS",
    }


def select_strategy(candidates: list[dict], scope: dict, regime: str) -> dict:
    eligible, rejected = [], []
    scope_keys = (
        "account_id",
        "instrument",
        "timeframe",
        "connection_id",
        "venue_instrument_id",
        "specification_version_id",
    )
    for candidate in candidates:
        reasons = []
        if any(not scope.get(k) or candidate.get(k) != scope[k] for k in scope_keys):
            reasons.append("Provider/account/instrument/timeframe authority does not match")
        if candidate.get("state") != "ACTIVE":
            reasons.append("Strategy is not active")
        evidence = candidate.get("validation_evidence", {})
        if not all(evidence.get(k) for k in (*FORMAL_GATES, "paper", "paper_forward")):
            reasons.append("Formal robustness and forward paper gates are incomplete")
        if evidence.get("event_driven_execution", True) is not True:
            reasons.append("Native event-driven execution validation did not pass")
        sample = candidate.get("regime_performance", {}).get(regime, {})
        if sample.get("trade_count", 0) < MIN_REGIME_TRADES or (sample.get("average_r") or 0) <= 0:
            reasons.append("Insufficient positive historical evidence for the current regime")
        health = candidate.get("health", {})
        if health.get("suspend"):
            reasons.append("Recorded recent performance has degraded")
        recent = candidate.get("recent", {})
        if recent.get("trade_count", 0) < 10 or (recent.get("average_r") or 0) <= 0:
            reasons.append("Insufficient positive forward performance")
        if (
            not candidate.get("artifact_hash")
            or candidate.get("performance_artifact_hash") != candidate["artifact_hash"]
        ):
            reasons.append("Performance does not match the immutable implementation")
        if reasons:
            rejected.append(
                {"strategy_version_id": candidate["strategy_version_id"], "reasons": reasons}
            )
        else:
            eligible.append(
                {
                    "strategy_version_id": candidate["strategy_version_id"],
                    "recent_average_r": recent["average_r"],
                    "historical_average_r": sample["average_r"],
                    "historical_trade_count": sample["trade_count"],
                }
            )
    eligible.sort(
        key=lambda item: (
            -item["recent_average_r"],
            -item["historical_average_r"],
            item["strategy_version_id"],
        )
    )
    return {
        "selected_version_id": eligible[0]["strategy_version_id"] if eligible else None,
        "regime": regime,
        "eligible": eligible,
        "rejected": rejected,
        "minimum_regime_trades": MIN_REGIME_TRADES,
        "execution_authorized": False,
    }


async def strategy_library(store, owner_id) -> list[dict]:
    versions = await store.list("strategy_version", owner_id)
    tests = await store.list("strategy_performance", owner_id)
    forward = [
        *await store.list("strategy_monitor", owner_id),
        *await store.list("strategy_paper_run", owner_id),
    ]
    result = []
    for version in versions:
        spec = version.data.get("specification", {})
        performance = next(
            (
                t.data
                for t in tests
                if t.data.get("strategy_version_id") == str(version.id)
                and t.data.get("backtest_id") == version.data.get("latest_backtest_id")
            ),
            {},
        )
        observations = [
            f.data
            for f in forward
            if f.data.get("strategy_version_id") == str(version.id)
            and f.data.get("artifact_hash") == version.data.get("artifact_hash")
        ]
        monitor = next((f for f in observations if f.get("mode") == "LIVE"), {})
        paper = next((f for f in observations if f.get("mode") != "LIVE" and f.get("trades")), {})
        recorded = monitor if len(monitor.get("trades", [])) >= 10 else paper
        returns = [
            float(t["r"]) for t in recorded.get("trades", [])[-30:] if t.get("r") is not None
        ]
        result.append(
            {
                "strategy_version_id": str(version.id),
                "state": version.state,
                "name": spec.get("name"),
                "family": spec.get("family"),
                "account_id": performance.get("account_id")
                or version.data.get("research_basis", {}).get("account_id"),
                "instrument": (spec.get("instruments") or [None])[0],
                "timeframe": performance.get("timeframe"),
                "connection_id": performance.get("connection_id"),
                "venue_instrument_id": spec.get("venue_instrument_id"),
                "specification_version_id": spec.get("specification_version_id"),
                "artifact_hash": version.data.get("artifact_hash"),
                "performance_artifact_hash": performance.get("artifact_hash"),
                "validation_evidence": version.data.get("validation_evidence", {}),
                "regime_performance": performance.get("regime_performance", {}),
                "metrics": performance.get("metrics", {}),
                "robustness": performance.get("robustness", {}),
                "execution_validation": performance.get("execution_validation"),
                "profile": monitor.get("pair_profile") or performance.get("pair_profile"),
                "health": rolling_health(monitor.get("trades", [])),
                "recent": return_statistics(returns),
                "recent_basis": "FORWARD_SHADOW" if recorded is monitor else "FORWARD_PAPER",
                "selection": version.data.get("strategy_selection"),
            }
        )
    return result
