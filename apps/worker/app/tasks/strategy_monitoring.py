"""Recurring owner/account-pinned evaluation for paper and activated versions."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from adapters.market_data.history import TIMEFRAMES, historical_candles
from apps.worker.app.celery_app import celery_app
from modules.backtesting.basis import resolve_backtest_basis
from modules.backtesting.engine import BacktestCandle, BacktestConfiguration
from modules.research.forex_factory_archive import ForexFactoryArchive
from modules.strategies.compiler import compile_strategy
from modules.strategies.monitoring import ENGINE, observe, validation_passed
from modules.strategies.pair_profile import profile_pair
from modules.strategies.performance import rolling_health, select_strategy, strategy_library
from modules.strategies.signals import requires_news_context
from packages.shared.config import settings
from packages.shared.database import unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore
from packages.strategy_sdk.schema import StrategySpecification


async def _evaluate(version_id: UUID) -> dict:
    async with unit_of_work() as db:
        # Serialize monitoring, paper completion, activation and suspension on the version.
        version = await db.scalar(
            select(ResourceRecord)
            .where(
                ResourceRecord.id == version_id,
                ResourceRecord.kind == "strategy_version",
            )
            .with_for_update(skip_locked=True)
        )
        if version is None or version.state not in {"PAPER_TRADING", "ACTIVE"}:
            return {"status": "INACTIVE_OR_BUSY"}
        store = ResourceStore(db)
        paper = version.state == "PAPER_TRADING"
        now = datetime.now(UTC)
        run = None
        monitor_id = uuid5(NAMESPACE_URL, f"strategy-monitor:{version.id}")
        try:
            spec = StrategySpecification.model_validate(version.data["specification"])
            evidence = version.data.get("validation_evidence", {})
            if not validation_passed(evidence):
                raise ValueError("Formal validation evidence is incomplete")
            if not paper and not (evidence.get("paper") and evidence.get("paper_forward")):
                raise ValueError(
                    "Recorded forward paper evidence is required before live monitoring"
                )
            if compile_strategy(spec).artifact_hash != version.data.get("artifact_hash"):
                raise ValueError("Strategy implementation changed after validation")
            if spec.trade_rules is None:
                raise ValueError("Strategy requires explicit price protection rules")
            basis, connection = await resolve_backtest_basis(db, version.owner_id, version)
            if paper:
                run = await store.get(
                    "strategy_paper_run", UUID(version.data["paper_run_id"]), version.owner_id
                )
                if run is None or run.state != "RUNNING" or run.data.get("engine") != ENGINE:
                    raise ValueError("Start a new forward paper session for this strategy")
                if run.data.get("artifact_hash") != version.data["artifact_hash"]:
                    raise ValueError("Paper session implementation no longer matches the version")
                data = run.data
                timeframe = data["timeframe"]
            else:
                run = await store.get("strategy_monitor", monitor_id, version.owner_id)
                data = run.data if run else {"started_at": now.isoformat()}
                # Shadow monitoring must use the same validated execution costs and limits.
                if not data.get("configuration") and version.data.get("paper_run_id"):
                    approved_paper = await store.get(
                        "strategy_paper_run", UUID(version.data["paper_run_id"]), version.owner_id
                    )
                    if (
                        approved_paper
                        and approved_paper.data.get("artifact_hash")
                        == version.data["artifact_hash"]
                    ):
                        data = {**data, "configuration": approved_paper.data.get("configuration")}
                timeframe = (
                    version.data.get("monitoring_timeframe") or basis["historical_timeframe"]
                )
            seconds = TIMEFRAMES[timeframe][1]
            config = BacktestConfiguration.model_validate(
                data.get("configuration")
                or {
                    "initial_equity": "10000",
                    "tick_size": basis.get("tick_size"),
                }
            )
            cached = data.get("recent_candles") or data.get("candles", [])[-100:]
            if (
                cached
                and data.get("next_fetch_at")
                and now < datetime.fromisoformat(data["next_fetch_at"])
            ):
                candles = [BacktestCandle.model_validate(item) for item in cached]
                source = data.get("source", {})
            else:
                candles, source = await historical_candles(
                    connection,
                    basis["instrument"],
                    now - timedelta(seconds=seconds * 100),
                    now,
                    timeframe,
                    account_id=UUID(basis["account_id"]),
                )
                completed = [
                    c for c in candles if c.observed_at + timedelta(seconds=seconds) <= now
                ]
                if completed:
                    last = max(c.observed_at for c in completed)
                    data = {
                        **data,
                        "recent_candles": [c.model_dump(mode="json") for c in completed[-100:]],
                        "next_fetch_at": max(
                            now + timedelta(seconds=60), last + timedelta(seconds=seconds * 2 + 2)
                        ).isoformat(),
                    }
            calendar = None
            if spec.event_rules or spec.instrument_type == "CFD" or requires_news_context(spec):
                reference = ForexFactoryArchive(settings.research_artifact_root).find_covering_date(
                    version.owner_id, now.date()
                )
                calendar = reference.events if reference else None
            data = observe(
                spec,
                data,
                candles,
                now=now,
                timeframe_seconds=seconds,
                configuration=config,
                calendar=calendar,
                # Activated versions continue to record a forward shadow ledger, not broker fills.
                paper=True,
            )
            completed = [c for c in candles if c.observed_at + timedelta(seconds=seconds) <= now]
            data["pair_profile"] = profile_pair(
                completed,
                basis["instrument"],
                as_of=now,
                calendar=calendar,
                spread=config.spread,
                slippage=config.slippage,
            )
            data["health"] = rolling_health(data.get("trades", []))
            data["performance_basis"] = (
                "FORWARD_PAPER" if paper else "FORWARD_SHADOW_NOT_BROKER_FILLS"
            )
            data.update(
                {
                    "source": source,
                    "strategy_version_id": str(version.id),
                    "account_id": basis["account_id"],
                    "instrument": basis["instrument"],
                    "mode": "PAPER" if paper else "LIVE",
                    "artifact_hash": version.data["artifact_hash"],
                    "timeframe": timeframe,
                    "failure": None,
                }
            )
            data["latest_signal"].update(
                {
                    "mode": data["mode"],
                    "strategy_version_id": str(version.id),
                    "artifact_hash": version.data["artifact_hash"],
                }
            )
            if run:
                await store.update(run, data, event_type="strategy.monitoring.observed")
            else:
                await store.create(
                    "strategy_monitor",
                    version.owner_id,
                    data,
                    record_id=monitor_id,
                    event_type="strategy.monitoring.started",
                )
            selection = None
            suspend = not paper and data["health"]["suspend"]
            if not paper and spec.instrument_type == "CFD":
                scope = {
                    "account_id": basis["account_id"],
                    "instrument": basis["instrument"],
                    "timeframe": timeframe,
                    "connection_id": basis["historical_connection_id"],
                    "venue_instrument_id": spec.venue_instrument_id,
                    "specification_version_id": spec.specification_version_id,
                }
                selection = select_strategy(
                    await strategy_library(store, version.owner_id),
                    scope,
                    data["pair_profile"]["regime_key"],
                )
                selection["scope"] = scope
                data["latest_signal"]["strategy_selection"] = selection
                if selection["selected_version_id"] != str(version.id):
                    data["latest_signal"].update(
                        {
                            "status": "WAIT",
                            "reason": "No eligible strategy for this regime"
                            if not selection["selected_version_id"]
                            else "A stronger validated strategy is selected for this regime",
                            "entry": None,
                            "stop_loss": None,
                            "take_profits": [],
                        }
                    )
            if suspend:
                data["latest_signal"].update(
                    {
                        "status": "SUSPENDED",
                        "reason": data["health"]["reason"],
                        "entry": None,
                        "stop_loss": None,
                        "take_profits": [],
                    }
                )
                # Remove an unfilled intent captured on the degradation tick.
                data["entry_intents"] = {
                    at: intent
                    for at, intent in data.get("entry_intents", {}).items()
                    if datetime.fromisoformat(at) <= completed[-1].observed_at
                }
            await store.update(
                version,
                {
                    **version.data,
                    "latest_signal": data["latest_signal"],
                    "last_evaluated_at": now.isoformat(),
                    "strategy_selection": selection,
                    "strategy_health": data["health"],
                    "lifecycle_state": "SUSPENDED" if suspend else version.state,
                },
                state="SUSPENDED" if suspend else version.state,
                event_type="strategy.edge.suspended" if suspend else "strategy.signal.evaluated",
            )
            # Persist the final selection decision, not the pre-selection signal.
            final_run = await store.get(
                "strategy_paper_run" if paper else "strategy_monitor",
                run.id if run else monitor_id,
                version.owner_id,
            )
            if final_run:
                await store.update(final_run, data, event_type="strategy.selection.recorded")
            return {"status": data["latest_signal"]["status"], "version_id": str(version.id)}
        except (LookupError, ValueError, RuntimeError, OSError) as exc:
            # HTTP client errors are OSError/RuntimeError-independent; handled below too.
            reason = str(exc)[:300] if type(exc) is ValueError else type(exc).__name__
        except Exception as exc:
            reason = type(exc).__name__  # Never persist credential-bearing request URLs.
        blocked = {
            "status": "BLOCKED",
            "reason": reason,
            "entry": None,
            "stop_loss": None,
            "take_profits": [],
            "execution_authorized": False,
            "mode": "PAPER" if paper else "LIVE",
        }
        await store.update(
            version,
            {**version.data, "latest_signal": blocked, "last_evaluated_at": now.isoformat()},
            event_type="strategy.monitoring.blocked",
        )
        if run:
            await store.update(
                run,
                {
                    **run.data,
                    "latest_signal": blocked,
                    "failure": reason,
                    "last_checked_at": now.isoformat(),
                },
                event_type="strategy.monitoring.blocked",
            )
        return blocked


@celery_app.task(name="apps.worker.app.tasks.strategy_monitoring.evaluate_strategy", time_limit=120)
def evaluate_strategy(version_id: str) -> dict:
    return asyncio.run(_evaluate(UUID(version_id)))


async def _schedule() -> list[str]:
    async with unit_of_work() as db:
        ids = list(
            await db.scalars(
                select(ResourceRecord.id).where(
                    ResourceRecord.kind == "strategy_version",
                    ResourceRecord.state.in_(["PAPER_TRADING", "ACTIVE"]),
                )
            )
        )
    for version_id in ids:
        evaluate_strategy.delay(str(version_id))
    return [str(value) for value in ids]


@celery_app.task(name="apps.worker.app.tasks.strategy_monitoring.schedule_monitoring")
def schedule_monitoring() -> list[str]:
    return asyncio.run(_schedule())
