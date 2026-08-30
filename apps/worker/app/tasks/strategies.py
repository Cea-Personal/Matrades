"""Durable AI strategy-research and provider-backed validation tasks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from adapters.market_data.history import historical_candles
from apps.worker.app.celery_app import celery_app
from modules.agents.rpc import OwnerScopedAgentGateway, RedisAgentGateway
from modules.backtesting.engine import BacktestConfiguration, PointInTimeBacktester
from modules.connections.resolution import resolve_connection
from modules.knowledge.ingestion import build_source_data
from modules.research.artifacts import ResearchCycleArchive
from modules.strategies.ai_workflow import StrategyGenerationWorkflow
from modules.strategies.compiler import compile_strategy
from modules.strategies.evidence import (
    EvidenceReference,
    StrategyEvidencePack,
    candle_checksum,
    historical_summary,
    lexical_knowledge_context,
    resolve_approved_candidate,
    split_research_history,
)
from modules.strategies.lifecycle import StrategyState
from modules.strategies.screening import screen_hypotheses
from packages.shared.config import settings
from packages.shared.database import unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore
from packages.strategy_sdk.schema import StrategySpecification
from packages.strategy_sdk.taxonomy import StrategyOrigin


async def _generate_strategy(run_id: UUID) -> dict:
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id)
        if run is None or run.kind != "strategy_research_run":
            raise RuntimeError("strategy research run not found")
        draft = await session.get(ResourceRecord, UUID(str(run.data["draft_id"])))
        if draft is None or draft.kind != "strategy_draft":
            raise RuntimeError("strategy draft not found")
        owner_id = run.owner_id
        origin = StrategyOrigin(str(run.data["origin"]))
        description = str(run.data.get("description") or "")
        selection_id = UUID(str(run.data["market_selection_id"]))
        market_run_id = UUID(str(run.data["market_research_run_id"]))
        account_id = UUID(str(run.data["account_id"]))
        connection_id = UUID(str(run.data["historical_connection_id"]))
        store = ResourceStore(session)
        await store.update(
            run,
            {**run.data, "started_at": datetime.now(UTC).isoformat()},
            state="RESEARCHING",
            event_type="strategy_assistance.requested",
        )
        await store.update(
            draft,
            {**draft.data, "lifecycle_state": "RESEARCHING"},
            state="RESEARCHING",
            event_type="strategy.researching",
        )

    async with unit_of_work() as session:
        store = ResourceStore(session)
        selection = await store.get("market_selection", selection_id, owner_id)
        market_run = await store.get("research_run", market_run_id, owner_id)
        account = await store.get("account", account_id, owner_id)
        if selection is None or selection.state != "ACTIVE_MARKET_ANALYSIS" or market_run is None:
            raise RuntimeError("immutable typed market research basis is unavailable")
        if account is None or account.state == "DELETED":
            raise RuntimeError("strategy research account is unavailable")
        candidate = resolve_approved_candidate(
            selection.data,
            market_run.data,
            now=datetime.now(UTC),
            max_age=timedelta(hours=settings.strategy_research_max_market_age_hours),
        )
        if candidate.account_id != str(account_id):
            raise RuntimeError("approved market research account does not match the pinned account")
        connection = await resolve_connection(session, owner_id, connection_id)
        account_data = {
            key: account.data.get(key)
            for key in (
                "name",
                "currency",
                "kind",
                "starting_balance",
                "prop_firm",
                "program",
                "reset_timezone",
            )
        }
        snapshots = [
            item
            for item in await store.list("broker_snapshot", owner_id)
            if item.data.get("account_id") == str(account_id)
        ]
        if snapshots:
            account_data["latest_broker_snapshot"] = {
                key: snapshots[0].data.get(key)
                for key in ("balance", "equity", "realized_daily_pnl", "observed_at", "source")
            }
        policies = [
            item
            for kind in ("prop_ruleset", "guardrail")
            for item in await store.list(kind, owner_id)
            if item.state == "ACTIVE" and item.data.get("account_id") in {None, str(account_id)}
        ]
        strategy_versions = [
            item
            for item in await store.list("strategy_version", owner_id)
            if candidate.instrument in item.data.get("specification", {}).get("instruments", [])
        ][:10]
        backtests = await store.list("strategy_backtest", owner_id)
        trade_proposals = {
            str(item.id): item for item in await store.list("trade_proposal", owner_id)
        }
        active_trades = await store.list("active_trade", owner_id)
        prior_context = []
        for item in strategy_versions:
            latest = next(
                (
                    test
                    for test in backtests
                    if test.data.get("strategy_version_id") == str(item.id)
                ),
                None,
            )
            linked_strategy_ids = {str(item.id), str(item.data.get("strategy_id") or "")}
            live_pnl: list[Decimal] = []
            for active_trade in active_trades:
                trade_proposal = trade_proposals.get(str(active_trade.data.get("proposal_id")))
                if (
                    trade_proposal is None
                    or str(trade_proposal.data.get("strategy_id")) not in linked_strategy_ids
                ):
                    continue
                position = active_trade.data.get("broker_position", {})
                live_pnl.append(
                    Decimal(str(position.get("pnl", 0))) - Decimal(str(position.get("fees", 0)))
                )
            prior_context.append(
                {
                    "reference_id": f"strategy:{item.id}:v{item.version}",
                    "strategy_version_id": str(item.id),
                    "name": item.data.get("specification", {}).get("name"),
                    "family": item.data.get("specification", {}).get("family"),
                    "fingerprint": item.data.get("fingerprint"),
                    "latest_backtest": (
                        {
                            "run_id": str(latest.id),
                            "state": latest.state,
                            "metrics": latest.data.get("metrics", {}),
                            "gates": latest.data.get("gates", {}),
                        }
                        if latest
                        else None
                    ),
                    "live_performance": {
                        "trade_count": len(live_pnl),
                        "net_pnl": str(sum(live_pnl, Decimal("0"))),
                        "expectancy": (
                            str(sum(live_pnl, Decimal("0")) / len(live_pnl)) if live_pnl else None
                        ),
                    },
                }
            )
        knowledge_sources = await store.list("knowledge_source", owner_id)
        knowledge = lexical_knowledge_context(
            knowledge_sources,
            " ".join(
                (
                    candidate.instrument,
                    candidate.category,
                    candidate.fingerprint.regime,
                    description,
                    "strategy risk entry exit",
                )
            ),
        )

    history_end = candidate.fingerprint.observed_at
    history_start = history_end - timedelta(days=settings.strategy_research_history_days)
    candles, history_source = await historical_candles(
        connection,
        candidate.instrument,
        history_start,
        history_end,
        settings.strategy_research_timeframe,
    )
    discovery, holdout = split_research_history(
        candles, discovery_ratio=settings.strategy_research_discovery_ratio
    )
    market_reference = f"market:{selection_id}"
    history_reference = f"history:{candle_checksum(discovery)[:16]}"
    references = [
        EvidenceReference(
            id=market_reference,
            kind="market_fingerprint",
            summary=(
                f"Approved {candidate.instrument} {candidate.fingerprint.regime} fingerprint "
                f"with score {candidate.score:.2f}"
            ),
            source_id=str(market_run_id),
            source_version=candidate.fingerprint.source_version,
            observed_at=candidate.fingerprint.observed_at,
        ),
        EvidenceReference(
            id=history_reference,
            kind="historical_discovery",
            summary=(
                f"{len(discovery)} chronological {settings.strategy_research_timeframe} candles; "
                "the later holdout is withheld from the agent"
            ),
            source_id=str(connection_id),
            source_version=str(history_source.get("source_version")),
            observed_at=discovery[-1].observed_at,
        ),
        EvidenceReference(
            id=f"account:{account_id}:v{account.version}",
            kind="account_context",
            summary="Pinned account profile and latest available read-only equity context",
            source_id=str(account_id),
            source_version=str(account.version),
        ),
    ]
    policy_context = []
    for policy in policies:
        reference_id = f"policy:{policy.id}:v{policy.version}"
        policy_context.append(
            {
                "reference_id": reference_id,
                "kind": policy.kind,
                "name": policy.data.get("name"),
                "rules": policy.data.get("rules", []),
            }
        )
        references.append(
            EvidenceReference(
                id=reference_id,
                kind=policy.kind,
                summary=f"Active {policy.kind} {policy.data.get('name', policy.id)}",
                source_id=str(policy.id),
                source_version=str(policy.version),
            )
        )
    for prior_item in prior_context:
        references.append(
            EvidenceReference(
                id=prior_item["reference_id"],
                kind="prior_strategy",
                summary=(
                    "Prior same-instrument strategy "
                    f"{prior_item.get('name') or prior_item['strategy_version_id']}"
                ),
                source_id=prior_item["strategy_version_id"],
            )
        )
    for knowledge_item in knowledge:
        references.append(
            EvidenceReference(
                id=knowledge_item["reference_id"],
                kind="knowledge_segment",
                summary=f"Context-only excerpt from {knowledge_item.get('source_name')}",
                source_id=knowledge_item["source_id"],
                source_version=knowledge_item["source_version"],
                authority="CONTEXT_ONLY",
            )
        )
    evidence_pack = StrategyEvidencePack(
        selection_id=str(selection_id),
        research_run_id=str(market_run_id),
        account_id=str(account_id),
        instrument=candidate.instrument,
        category=candidate.category,
        collected_at=datetime.now(UTC),
        market_fingerprint={
            **candidate.fingerprint.model_dump(mode="json"),
            "candidate_score": candidate.score,
            "candidate_evidence": candidate.evidence,
        },
        historical_discovery={
            "reference_id": history_reference,
            "timeframe": settings.strategy_research_timeframe,
            "provider": history_source.get("provider"),
            "source_version": history_source.get("source_version"),
            "checksum": candle_checksum(discovery),
            "summary": historical_summary(discovery),
        },
        account_context=account_data,
        policy_context=policy_context,
        prior_strategy_context=prior_context,
        knowledge_context=knowledge,
        references=references,
    )
    serialized_pack = evidence_pack.model_dump(mode="json")
    holdout_evidence = {
        "timeframe": settings.strategy_research_timeframe,
        "candle_count": len(holdout),
        "start_at": holdout[0].observed_at.isoformat(),
        "end_at": holdout[-1].observed_at.isoformat(),
        "checksum": candle_checksum(holdout),
        "source": history_source,
        "visibility": "WITHHELD_FROM_AGENT",
    }
    async with unit_of_work() as session:
        persisted_run = await session.get(ResourceRecord, run_id)
        if persisted_run is None:
            raise RuntimeError("strategy research run disappeared")
        store = ResourceStore(session)
        retrieval = await store.audit(
            owner_id,
            None,
            "strategy_evidence.retrieved",
            "strategy_research_run",
            run_id,
            {
                "market_selection_id": str(selection_id),
                "history_checksum": serialized_pack["historical_discovery"]["checksum"],
                "knowledge_segment_ids": [item["segment_id"] for item in knowledge],
            },
        )
        serialized_pack["retrieval_audit_id"] = str(retrieval.id)
        await store.update(
            persisted_run,
            {
                **persisted_run.data,
                "evidence_pack": serialized_pack,
                "holdout_evidence": holdout_evidence,
            },
            state="RESEARCHING",
            event_type="strategy_evidence.prepared",
        )

    gateway = OwnerScopedAgentGateway(
        RedisAgentGateway(settings.redis_url, settings.research_agent_timeout_seconds), owner_id
    )
    try:
        hypotheses = await StrategyGenerationWorkflow(gateway).generate_hypotheses(
            origin, serialized_pack, description
        )
    finally:
        await gateway.close()
    median_price = sorted(item.close for item in discovery)[len(discovery) // 2]
    screening_configuration = BacktestConfiguration(
        initial_equity=Decimal(str(account_data.get("starting_balance") or "10000")),
        spread=median_price * Decimal("0.0002"),
        commission=Decimal("0"),
        slippage=median_price * Decimal("0.00005"),
    )
    screening = screen_hypotheses(hypotheses, holdout, screening_configuration)
    if screening.selected_hypothesis_id is None:
        raise RuntimeError("no strategy hypothesis passed preliminary holdout screening")
    proposal = next(
        item for item in hypotheses if item.hypothesis_id == screening.selected_hypothesis_id
    )
    completed_at = datetime.now(UTC)
    details = {
        "origin": origin.value,
        "description": description,
        "research_basis": {
            "market_selection_id": str(selection_id),
            "market_research_run_id": str(market_run_id),
            "instrument": candidate.instrument,
            "category": candidate.category,
        },
        "evidence_pack": serialized_pack,
        "holdout_evidence": holdout_evidence,
        "hypotheses": [item.model_dump(mode="json") for item in hypotheses],
        "preliminary_screen": {
            **screening.model_dump(mode="json"),
            "configuration": screening_configuration.model_dump(mode="json"),
            "cost_assumptions": (
                "Conservative price-proportional spread and slippage; commission zero"
            ),
        },
        "selected_hypothesis_id": proposal.hypothesis_id,
        "proposed_specification": proposal.specification.model_dump(mode="json"),
        "breakdown": proposal.breakdown,
        "evidence": proposal.evidence_refs,
        "rationale": proposal.rationale,
        "agent_id": proposal.agent_id,
        "state": "AWAITING_STRATEGY_APPROVAL",
        "completed_at": completed_at.isoformat(),
    }
    artifact = ResearchCycleArchive(settings.research_artifact_root).save_cycle(
        owner_id=owner_id,
        cycle_type="strategy_research",
        cycle_id=run_id,
        occurred_at=completed_at,
        details=details,
    )
    artifact_data = {
        "relative_path": artifact.relative_path,
        "checksum": artifact.checksum,
        "manifest_name": artifact.manifest_name,
    }
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id)
        draft = await session.get(ResourceRecord, UUID(str(run.data["draft_id"]))) if run else None
        if run is None or draft is None:
            raise RuntimeError("strategy research records disappeared")
        store = ResourceStore(session)
        await store.update(
            run,
            {**run.data, **details, "artifact": artifact_data},
            state="AWAITING_STRATEGY_APPROVAL",
            event_type="strategy_suggestion.created",
        )
        await store.update(
            draft,
            {
                **draft.data,
                "proposed_specification": details["proposed_specification"],
                "breakdown": proposal.breakdown,
                "evidence": proposal.evidence_refs,
                "rationale": proposal.rationale,
                "evidence_pack": serialized_pack,
                "holdout_evidence": holdout_evidence,
                "hypotheses": details["hypotheses"],
                "preliminary_screen": details["preliminary_screen"],
                "selected_hypothesis_id": proposal.hypothesis_id,
                "agent_id": proposal.agent_id,
                "research_run_id": str(run_id),
                "research_artifact": artifact_data,
                "lifecycle_state": "AWAITING_STRATEGY_APPROVAL",
            },
            state="AWAITING_STRATEGY_APPROVAL",
            event_type="strategy.approval_requested",
        )
        proposal_content = (
            f"Strategy proposal: {proposal.specification.name}\n"
            f"Family: {proposal.specification.family.value}\n"
            f"Origin: {proposal.specification.origin.value}\n\n"
            f"Step-by-step breakdown:\n{proposal.breakdown}\n\n"
            f"Specification:\n{proposal.specification.model_dump_json(indent=2)}\n\n"
            f"Generated evaluator code:\n{compile_strategy(proposal.specification).generated_code}"
        )
        proposal_data = {
            **build_source_data(
                name=f"Strategy proposal — {proposal.specification.name}",
                content=proposal_content,
                media_type="text/plain",
                category="strategies",
                tags=["generated-strategy", "proposal", proposal.specification.family.value],
                source_date=completed_at.date().isoformat(),
                source_kind="GENERATED_STRATEGY_PROPOSAL",
                external_id=str(run_id),
            ),
            "linked_strategy_research_run_id": str(run_id),
            "linked_strategy_draft_id": str(draft.id),
        }
        existing_source = next(
            (
                item
                for item in await store.list("knowledge_source", owner_id)
                if item.data.get("source_kind") == "GENERATED_STRATEGY_PROPOSAL"
                and item.data.get("external_id") == str(run_id)
            ),
            None,
        )
        if existing_source is None:
            await store.create(
                "knowledge_source",
                owner_id,
                proposal_data,
                state="ACTIVE",
                actor_id=None,
                event_type="strategy_proposal_knowledge.indexed",
            )
        else:
            await store.update(
                existing_source,
                proposal_data,
                state="ACTIVE",
                actor_id=None,
                event_type="strategy_proposal_knowledge.reindexed",
            )
    return {**details, "artifact": artifact_data}


async def _mark_strategy_research_failed(run_id: UUID, error: Exception) -> None:
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id)
        if run is None or run.kind != "strategy_research_run":
            return
        draft = await session.get(ResourceRecord, UUID(str(run.data["draft_id"])))
        completed_at = datetime.now(UTC)
        details = {
            "state": "DEGRADED",
            "completed_at": completed_at.isoformat(),
            "failure": type(error).__name__,
        }
        artifact = ResearchCycleArchive(settings.research_artifact_root).save_cycle(
            owner_id=run.owner_id,
            cycle_type="strategy_research",
            cycle_id=run_id,
            occurred_at=completed_at,
            details=details,
        )
        artifact_data = {"relative_path": artifact.relative_path, "checksum": artifact.checksum}
        store = ResourceStore(session)
        await store.update(
            run,
            {**run.data, **details, "artifact": artifact_data},
            state="DEGRADED",
            event_type="strategy.research_failed",
        )
        if draft is not None:
            await store.update(
                draft,
                {
                    **draft.data,
                    "failure": type(error).__name__,
                    "research_artifact": artifact_data,
                },
                state="DEGRADED",
                event_type="strategy.degraded",
            )


@celery_app.task(name="apps.worker.app.tasks.strategies.generate_strategy_draft")
def generate_strategy_draft(run_id: str) -> dict:
    parsed = UUID(run_id)
    try:
        return asyncio.run(_generate_strategy(parsed))
    except Exception as exc:
        asyncio.run(_mark_strategy_research_failed(parsed, exc))
        raise


async def _run_backtest(run_id: UUID) -> dict:
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id)
        if run is None or run.kind != "strategy_backtest":
            raise RuntimeError("strategy backtest run not found")
        strategy = await session.get(ResourceRecord, UUID(str(run.data["strategy_version_id"])))
        if strategy is None or strategy.kind != "strategy_version":
            raise RuntimeError("strategy version not found")
        connection = await resolve_connection(
            session, run.owner_id, UUID(str(run.data["connection_id"]))
        )
        specification = StrategySpecification.model_validate(strategy.data["specification"])
        owner_id = run.owner_id
        await ResourceStore(session).update(
            run,
            {**run.data, "started_at": datetime.now(UTC).isoformat()},
            state="RUNNING",
            event_type="backtest.started",
        )

    candles, source = await historical_candles(
        connection,
        str(run.data["instrument"]),
        datetime.fromisoformat(str(run.data["start_at"])),
        datetime.fromisoformat(str(run.data["end_at"])),
        str(run.data["timeframe"]),
    )
    configuration = BacktestConfiguration(
        initial_equity=Decimal(str(run.data["initial_equity"])),
        spread=Decimal(str(run.data["spread"])),
        commission=Decimal(str(run.data["commission"])),
        slippage=Decimal(str(run.data["slippage"])),
        max_daily_loss=Decimal(str(run.data.get("max_daily_loss", "1000000"))),
        max_total_loss=Decimal(str(run.data.get("max_total_loss", "1000000"))),
    )
    result = PointInTimeBacktester().run(specification, candles, configuration)
    compiled = compile_strategy(specification)
    artifact_hash = compiled.artifact_hash
    completed_at = datetime.now(UTC)
    details = {
        **result.model_dump(mode="json"),
        "source": source,
        "artifact_hash": artifact_hash,
        "generated_code": compiled.generated_code,
        "generated_code_language": "python",
        "completed_at": completed_at.isoformat(),
    }
    artifact = ResearchCycleArchive(settings.research_artifact_root).save_cycle(
        owner_id=owner_id,
        cycle_type="strategy_backtest",
        cycle_id=run_id,
        occurred_at=completed_at,
        details=details,
    )
    artifact_data = {
        "relative_path": artifact.relative_path,
        "checksum": artifact.checksum,
        "manifest_name": artifact.manifest_name,
    }
    state = "PASSED" if all(result.gates.values()) else "FAILED"
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id)
        strategy = (
            await session.get(ResourceRecord, UUID(str(run.data["strategy_version_id"])))
            if run
            else None
        )
        if run is None or strategy is None:
            raise RuntimeError("backtest records disappeared")
        store = ResourceStore(session)
        await store.update(
            run,
            {**run.data, **details, "artifact": artifact_data},
            state=state,
            event_type="backtest.completed",
        )
        await store.update(
            strategy,
            {
                **strategy.data,
                "lifecycle_state": StrategyState.VALIDATING,
                "latest_backtest_id": str(run_id),
                "latest_backtest_state": state,
                "validation_evidence": {
                    **strategy.data.get("validation_evidence", {}),
                    "backtest": state == "PASSED",
                    "out_of_sample": state == "PASSED",
                    "walk_forward": state == "PASSED",
                    "stress": state == "PASSED",
                    "policy": state == "PASSED",
                },
            },
            state=StrategyState.VALIDATING,
            event_type="validation_stage.completed",
        )
    return {**details, "artifact": artifact_data, "state": state}


async def _mark_backtest_failed(run_id: UUID, error: Exception) -> None:
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id)
        if run is None or run.kind != "strategy_backtest":
            return
        completed_at = datetime.now(UTC)
        details = {
            "state": "FAILED",
            "completed_at": completed_at.isoformat(),
            "failure": type(error).__name__,
        }
        artifact = ResearchCycleArchive(settings.research_artifact_root).save_cycle(
            owner_id=run.owner_id,
            cycle_type="strategy_backtest",
            cycle_id=run_id,
            occurred_at=completed_at,
            details=details,
        )
        artifact_data = {
            "relative_path": artifact.relative_path,
            "checksum": artifact.checksum,
            "manifest_name": artifact.manifest_name,
        }
        await ResourceStore(session).update(
            run,
            {
                **run.data,
                **details,
                "artifact": artifact_data,
            },
            state="FAILED",
            event_type="backtest.failed",
        )


@celery_app.task(name="apps.worker.app.tasks.strategies.run_strategy_backtest")
def run_strategy_backtest(run_id: str) -> dict:
    parsed = UUID(run_id)
    try:
        return asyncio.run(_run_backtest(parsed))
    except Exception as exc:
        asyncio.run(_mark_backtest_failed(parsed, exc))
        raise


@celery_app.task(bind=True, name="apps.worker.app.tasks.strategies.validate_strategy")
def validate_strategy(self, strategy_version_id: str, input_hash: str) -> dict:
    """Compatibility task; new validation starts through run_strategy_backtest."""
    self.update_state(state="PROGRESS", meta={"stage": "provider_backtest", "progress": 100})
    return {
        "strategy_version_id": strategy_version_id,
        "input_hash": input_hash,
        "immutable_inputs": True,
        "passed": False,
        "reason": "create a provider-backed strategy_backtest run",
    }
