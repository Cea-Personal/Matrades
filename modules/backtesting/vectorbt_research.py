"""Bounded vectorbt discovery sweeps; never optimize on the reserved outer holdout."""

from __future__ import annotations

from decimal import Decimal
from itertools import product
from typing import TYPE_CHECKING, Any

from modules.strategies.ai_workflow import StrategyHypothesis
from modules.strategies.entry_context import entry_context_reason
from modules.strategies.pair_profile import news_features
from modules.strategies.signals import (
    entry_matches,
    matches,
    required_technical_features,
    strategy_feature_series,
    technical_feature_series,
)
from packages.strategy_sdk.schema import StrategySpecification

if TYPE_CHECKING:
    from pandas import DataFrame

    from modules.backtesting.engine import BacktestCandle, BacktestConfiguration


def parameter_sweep(
    hypotheses: list[StrategyHypothesis],
    discovery: list[BacktestCandle],
    configuration: BacktestConfiguration,
    *,
    timeframe_seconds: int,
    max_combinations: int = 256,
    calendar: list[dict] | None = None,
) -> tuple[list[StrategyHypothesis], dict]:
    import numpy as np
    import pandas as pd
    import vectorbt as vbt

    from modules.research.quantitative_features import candle_frame

    if max_combinations < len(hypotheses) or max_combinations > 4096:
        raise ValueError("parameter search budget must cover every family and be <=4096")
    archived_discovery_count = len(discovery)
    # Preserve timeframe and the untouched outer holdout; bound work on recent discovery.
    discovery = discovery[-20_000:]
    if len(discovery) < 60:
        return hypotheses, {
            "engine": "vectorbt",
            "status": "INSUFFICIENT_DISCOVERY_HISTORY",
            "candle_count": len(discovery),
            "required_candles": 60,
            "approved_for_execution": False,
        }
    frame = candle_frame(discovery, timeframe_seconds)
    combinations = list(product((10, 20, 30, 50), ("1", "1.5", "2", "2.5"), ("1", "1.5", "2", "3")))
    budget = min(len(combinations), max_combinations // max(1, len(hypotheses)))
    # Evenly sample the grid for EACH hypothesis, rather than starving later families.
    sampled = [combinations[int(index)] for index in np.linspace(0, len(combinations) - 1, budget)]
    selected = []
    experiments = []
    inner_cut = int(len(discovery) * 0.6)
    feature_cache = {}
    required = set().union(*(required_technical_features(h.specification) for h in hypotheses))
    technical_series = technical_feature_series(discovery, required)
    for hypothesis in hypotheses:
        prototype = hypothesis.specification
        if prototype.trade_rules is None:
            selected.append(hypothesis)
            continue
        variants, signals, exits, stops, targets = [], [], [], [], []
        for window, stop, reward in sampled:
            data = prototype.model_dump(mode="json")
            data["parameters"] = {
                **data["parameters"],
                "structure_window": str(window),
                "atr_period": "14",
            }
            data["trade_rules"]["stop_volatility_multiple"] = stop
            data["trade_rules"]["take_profit_r_multiples"] = [reward]
            spec = StrategySpecification.model_validate(data)
            variants.append(spec)
            if window not in feature_cache:
                feature_cache[window] = strategy_feature_series(
                    spec, discovery, technical_series=technical_series
                )
            features = feature_cache[window]
            signal, exit_signal, distance = [False], [False], [np.nan]
            for index in range(1, len(discovery)):
                point = {
                    **features[index - 1],
                    **news_features(spec.instruments[0], discovery[index].observed_at, calendar),
                }
                signal.append(
                    entry_matches(spec, point)
                    and not entry_context_reason(spec, discovery[index].observed_at, calendar)
                    and point["volatility"] > 0
                )
                exit_signal.append(matches(spec.exit, point) or matches(spec.invalidation, point))
                distance.append(float(point["volatility"] * Decimal(stop) / discovery[index].open))
            signals.append(signal)
            exits.append(exit_signal)
            stops.append(distance)
            targets.append(np.array(distance) * float(reward))
        columns = range(len(variants))

        def matrix(values: list, columns: range = columns) -> DataFrame:
            return pd.DataFrame(np.array(values).T, index=frame.index, columns=columns)

        short = prototype.trade_rules.direction == "SHORT"
        portfolio = vbt.Portfolio.from_signals(
            close=frame.close,
            open=frame.open,
            high=frame.high,
            low=frame.low,
            entries=False if short else matrix(signals),
            exits=False if short else matrix(exits),
            short_entries=matrix(signals) if short else False,
            short_exits=matrix(exits) if short else False,
            price=frame.open,
            stop_entry_price="Price",
            sl_stop=matrix(stops),
            tp_stop=matrix(targets),
            slippage=float(configuration.slippage) / frame.open
            + float(configuration.spread) / frame.open / 2,
            fixed_fees=float(configuration.commission),
            size=1.0,
            init_cash=float(configuration.initial_equity),
            accumulate=False,
            freq=f"{timeframe_seconds}s",
        )
        records = portfolio.trades.records
        scores = []
        for index, (spec, parameters) in enumerate(zip(variants, sampled, strict=True)):
            trades = records[(records.col == index) & (records.status == 1)]
            train = trades[(trades.entry_idx < inner_cut) & (trades.exit_idx < inner_cut)]
            validation = trades[trades.entry_idx >= inner_cut]

            def stats(rows: DataFrame) -> dict[str, Any]:
                if rows.empty:
                    return {"trade_count": 0, "net_pnl": 0.0, "expectancy": 0.0}
                return {
                    "trade_count": len(rows),
                    "net_pnl": float(rows.pnl.sum()),
                    "expectancy": float(rows.pnl.mean()),
                    "win_rate": float((rows.pnl > 0).mean()),
                }

            training, testing = stats(train), stats(validation)
            eligible = all(
                item["trade_count"] >= 3 and item["net_pnl"] > 0 for item in (training, testing)
            )
            row: dict[str, Any] = {
                "hypothesis_id": hypothesis.hypothesis_id,
                "family": spec.family.value,
                "direction": "SHORT" if short else "LONG",
                "window": parameters[0],
                "atr_stop": parameters[1],
                "reward_r": parameters[2],
                "train": training,
                "inner_validation": testing,
                "eligible": eligible,
                "regimes": spec.regimes,
                "sessions": spec.sessions,
                "regime_performance": {},
            }
            grouped = {}
            from modules.strategies.pair_profile import regime_from_features, regime_key

            for trade in validation.itertuples():
                key = regime_key(
                    regime_from_features(
                        feature_cache[parameters[0]][max(0, int(trade.entry_idx) - 1)]
                    )
                )
                grouped.setdefault(key, []).append(float(trade.pnl))
            row["regime_performance"] = {
                key: {
                    "trade_count": len(pnls),
                    "net_pnl": sum(pnls),
                    "expectancy": sum(pnls) / len(pnls),
                }
                for key, pnls in grouped.items()
            }
            scores.append(row)
        for row in scores:
            neighbours = [
                other
                for other in scores
                if sum(
                    a != b
                    for a, b in zip(
                        (row["window"], row["atr_stop"], row["reward_r"]),
                        (other["window"], other["atr_stop"], other["reward_r"]),
                        strict=True,
                    )
                )
                == 1
            ]
            row["robust_neighbour_fraction"] = (
                sum(n["eligible"] for n in neighbours) / len(neighbours) if neighbours else 0.0
            )
            row["robust_region"] = (
                row["eligible"] and len(neighbours) >= 2 and row["robust_neighbour_fraction"] >= 0.5
            )
        eligible_rows = [(i, row) for i, row in enumerate(scores) if row["robust_region"]]
        if eligible_rows:
            best_index, best = max(
                eligible_rows,
                key=lambda pair: (
                    pair[1]["robust_neighbour_fraction"],
                    pair[1]["inner_validation"]["expectancy"],
                    -pair[0],
                ),
            )
            selected.append(
                hypothesis.model_copy(
                    update={
                        "hypothesis_id": f"{hypothesis.hypothesis_id}_QUANT",
                        "specification": variants[best_index],
                        "rationale": hypothesis.rationale
                        + " Parameters selected from a stable discovery-only region.",
                    }
                )
            )
            best["selected"] = True
        else:
            # Keep the fixed hypothesis for the independent screen, not a fragile grid winner.
            selected.append(hypothesis)
        experiments.extend(scores)
    return selected, {
        "engine": "vectorbt",
        "version": vbt.__version__,
        "status": "COMPLETED",
        "combination_count": len(experiments),
        "budget": max_combinations,
        "discovery_count": len(discovery),
        "inner_train_count": inner_cut,
        "archived_discovery_count": archived_discovery_count,
        "searched_discovery_count": len(discovery),
        "search_start_at": discovery[0].observed_at.isoformat(),
        "search_end_at": discovery[-1].observed_at.isoformat(),
        "outer_holdout_used": False,
        "experiments": experiments,
        "approved_for_execution": False,
        "limitations": [
            "Fast OHLC sweep; final event-driven and broker validation required",
            "No multiple-testing significance or guaranteed optimal strategy",
        ],
    }
