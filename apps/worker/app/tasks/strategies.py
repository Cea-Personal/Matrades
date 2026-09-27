"""Durable AI strategy-research and provider-backed validation tasks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from pydantic import ValidationError
from sqlalchemy import select

from adapters.market_data.history import TIMEFRAMES, historical_candles
from apps.worker.app.celery_app import celery_app
from modules.agents.rpc import OwnerScopedAgentGateway, RedisAgentGateway
from modules.backtesting.basis import resolve_backtest_basis
from modules.backtesting.engine import BacktestConfiguration, PointInTimeBacktester
from modules.backtesting.nautilus_validation import validate_execution
from modules.backtesting.vectorbt_research import parameter_sweep
from modules.connections.resolution import resolve_connection
from modules.knowledge.ingestion import build_source_data
from modules.knowledge.openai_embeddings import embed_source_data
from modules.knowledge.retrieval import KnowledgeSearchInput, retrieve_knowledge
from modules.market_data.research_context import collect_context
from modules.market_data.research_history import (
    archived_history,
    cached_history,
    persist_dataset,
    persist_features,
)
from modules.market_data.research_store import ResearchDataStore
from modules.research.artifacts import ResearchCycleArchive
from modules.research.forex_factory_archive import ForexFactoryArchive
from modules.strategies.ai_workflow import InvalidStrategyCondition, StrategyGenerationWorkflow
from modules.strategies.calendar_evidence import historical_calendar
from modules.strategies.compiler import compile_strategy
from modules.strategies.evidence import (
    EvidenceReference,
    StrategyEvidencePack,
    candle_checksum,
    historical_summary,
    resolve_approved_candidate,
    split_research_history,
)
from modules.strategies.family_library import cfd_family_hypotheses
from modules.strategies.lifecycle import StrategyState
from modules.strategies.pair_profile import profile_pair
from modules.strategies.research_pipeline import prepare_strategy_research
from modules.strategies.screening import retain_family_alternatives, screen_hypotheses
from packages.shared.config import settings
from packages.shared.database import unit_of_work
from packages.shared.store import ResourceRecord, ResourceStore
from packages.strategy_sdk.schema import StrategySpecification
from packages.strategy_sdk.taxonomy import StrategyOrigin


async def _generate_strategy(run_id: UUID) -> dict:
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id, with_for_update=True)
        if run is None or run.kind != "strategy_research_run":
            raise RuntimeError("strategy research run not found")
        if run.state != "QUEUED":
            return {"state": run.state, "run_id": str(run_id)}
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
        timeframe = str(
            run.data.get("historical_timeframe") or settings.strategy_research_timeframe
        )
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
        history_binding_id = run.data.get("research_history_binding_id")
        if history_binding_id:
            history_binding = await store.get(
                "provider_binding", UUID(history_binding_id), owner_id
            )
            if (
                history_binding is None
                or history_binding.state == "DELETED"
                or history_binding.data.get("account_id") != str(account_id)
                or history_binding.data.get("connection_id") != str(connection_id)
                or history_binding.data.get("lane") != selection.data.get("lane")
                or history_binding.data.get("capability") != "CANDLES"
                or history_binding.data.get("authority_purpose") != "HISTORY"
                or history_binding.data.get("verification_status") != "VERIFIED"
            ):
                raise RuntimeError("pinned independent research history binding is unavailable")
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
        transcript_sources = [
            item
            for item in knowledge_sources
            if item.data.get("source_kind") == "YOUTUBE_TRANSCRIPT" and item.state == "ACTIVE"
        ]
        pinned_source_id = run.data.get("knowledge_source_id")
        if pinned_source_id:
            transcript_sources = [
                item for item in transcript_sources if str(item.id) == str(pinned_source_id)
            ]
            if not transcript_sources:
                raise RuntimeError("pinned YouTube transcript evidence is unavailable")
        transcript_query = " ".join(
            (
                candidate.instrument,
                candidate.category,
                candidate.fingerprint.regime,
                description,
                "trading strategy entry exit stop loss take profit risk",
            )
        )
        knowledge_retrieval = await retrieve_knowledge(
            session, owner_id,
            KnowledgeSearchInput(
                query=transcript_query[:4000], limit=12,
                asset_class=candidate.asset_class,
                instrument_type=candidate.instrument_type,
            ),
            source_id=UUID(str(pinned_source_id)) if pinned_source_id else None,
            research=True,
        )
        knowledge = knowledge_retrieval["citations"]
        if pinned_source_id and not knowledge:
            raise RuntimeError("pinned YouTube transcript has no compatible indexed context")
        used_sources = {hit["source_id"] for hit in knowledge}
        transcript_sources = [
            source for source in transcript_sources if str(source.id) in used_sources
        ]

    history_end = candidate.fingerprint.observed_at
    history_start = history_end - timedelta(days=settings.strategy_research_history_days)
    async with unit_of_work() as session:
        cached = await cached_history(
            session,
            owner_id,
            account_id,
            connection,
            candidate.instrument,
            history_start,
            history_end,
            timeframe,
        )
    candles, history_source = cached or await archived_history(
        connection,
        owner_id,
        candidate.instrument,
        history_start,
        history_end,
        timeframe,
        account_id=account_id,
        native_loader=historical_candles,
    )
    timeframe_seconds = TIMEFRAMES[timeframe][1]
    candles = [
        item
        for item in candles
        if history_start <= item.observed_at
        and item.observed_at + timedelta(seconds=timeframe_seconds) <= history_end
    ]
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
                f"{len(discovery)} chronological {timeframe} candles; "
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
                source_version=str(knowledge_item["source_version"]),
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
            "timeframe": timeframe,
            "provider": history_source.get("provider"),
            "source_version": history_source.get("source_version"),
            "checksum": candle_checksum(discovery),
            "summary": historical_summary(discovery),
            "recent_candles": [item.model_dump(mode="json") for item in discovery[-100:]],
        },
        account_context=account_data,
        policy_context=policy_context,
        prior_strategy_context=prior_context,
        knowledge_context=knowledge,
        knowledge_retrieval={
            key: value for key, value in knowledge_retrieval.items() if key != "citations"
        },
        references=references,
        asset_class=candidate.asset_class,
        instrument_type=candidate.instrument_type,
        quantity_unit=candidate.quantity_unit,
        venue_instrument_id=candidate.venue_instrument_id,
        specification_version_id=candidate.specification_version_id,
        futures_contract_id=candidate.futures_contract_id,
        source_cut_refs=selection.data.get("source_cut_refs", []),
    )
    serialized_pack = evidence_pack.model_dump(mode="json")
    discovery_calendar, calendar_coverage = historical_calendar(
        ForexFactoryArchive(settings.research_artifact_root),
        owner_id,
        discovery[0].observed_at,
        discovery[-1].observed_at,
    )
    serialized_pack["pair_profile"] = profile_pair(
        discovery, candidate.instrument, calendar=discovery_calendar
    )
    serialized_pack["pair_profile"]["calendar_coverage"] = calendar_coverage
    async with unit_of_work() as session:
        dataset = await persist_dataset(
            session,
            owner_id,
            account_id,
            connection_id,
            candidate.instrument,
            timeframe,
            candles,
            history_source,
        )
        context_evidence, intermarket = await collect_context(
            session,
            owner_id,
            account_id,
            candidate.instrument,
            history_start,
            discovery[-1].observed_at,
        )
        serialized_pack["independent_context"] = context_evidence
        # Persist the DISCOVERY prefix separately: agents never see outer-holdout features.
        serialized_pack["quantitative_features"] = await persist_features(
            session, owner_id, dataset, discovery, timeframe, context=intermarket
        )
    holdout_evidence = {
        "timeframe": timeframe,
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
                "youtube_transcript_source_ids": [str(item.id) for item in transcript_sources],
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
        persisted_draft = await store.get(
            "strategy_draft", UUID(str(persisted_run.data["draft_id"])), owner_id
        )
        if persisted_draft is not None:
            await store.update(
                persisted_draft,
                {**persisted_draft.data, "evidence_pack": serialized_pack},
                event_type="strategy_evidence.attached",
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
    if hypotheses:
        hypotheses.extend(cfd_family_hypotheses(hypotheses[0].specification, history_reference))
    median_price = sorted(item.close for item in discovery)[len(discovery) // 2]
    tick = selection.data.get("candidate", {}).get("specification", {}).get("tick_size")
    screening_configuration = BacktestConfiguration(
        initial_equity=Decimal(str(account_data.get("starting_balance") or "10000")),
        spread=median_price * Decimal("0.0002"),
        commission=Decimal("0"),
        slippage=median_price * Decimal("0.00005"),
        tick_size=Decimal(str(tick)) if tick else None,
    )
    hypotheses, quantitative_search = await asyncio.to_thread(
        parameter_sweep,
        hypotheses,
        discovery,
        screening_configuration,
        timeframe_seconds=timeframe_seconds,
        max_combinations=settings.quantitative_research_max_combinations,
        calendar=discovery_calendar,
    )
    quantitative_archive = ResearchDataStore(settings.research_data_root, owner_id).json(
        quantitative_search, layer="experiments"
    )
    async with unit_of_work() as session:
        store = ResourceStore(session)
        experiment_id = uuid5(
            NAMESPACE_URL, f"strategy-experiment:{run_id}:{quantitative_archive['checksum']}"
        )
        existing_experiment = await store.get("strategy_experiment", experiment_id, owner_id)
        if existing_experiment is None:
            await store.create(
                "strategy_experiment",
                owner_id,
                {
                    **dataset,
                    "account_id": str(account_id),
                    "instrument": candidate.instrument,
                    "strategy_research_run_id": str(run_id),
                    "timeframe": timeframe,
                    "engine": "vectorbt",
                    "status": quantitative_search["status"],
                    "combination_count": quantitative_search.get("combination_count", 0),
                    "archive": quantitative_archive,
                    "outer_holdout_used": False,
                    "execution_authorized": False,
                },
                record_id=experiment_id,
            )
    holdout_evidence["quantitative_search"] = {
        key: value for key, value in quantitative_search.items() if key != "experiments"
    }
    holdout_calendar, holdout_calendar_coverage = historical_calendar(
        ForexFactoryArchive(settings.research_artifact_root),
        owner_id,
        holdout[0].observed_at,
        holdout[-1].observed_at,
    )
    holdout_evidence["calendar_coverage"] = holdout_calendar_coverage
    screening = screen_hypotheses(
        hypotheses, holdout, screening_configuration, calendar=holdout_calendar
    )
    pipeline: dict[str, Any] = {
        "name": "youtube_transcript_to_trade_plan",
        "stages": {
            "youtube_transcript": "COMPLETED" if transcript_sources else "NOT_AVAILABLE",
            "strategy_hypothesis": "COMPLETED",
            "structured_strategy_rules": "COMPLETED",
            "preliminary_backtest": "COMPLETED",
            "formal_backtest": "WAITING_FOR_APPROVAL",
            "validation": "WAITING_FOR_FORMAL_BACKTEST",
            "paper_trading": "WAITING_FOR_VALIDATION",
            "approved_trade_plan": "WAITING_FOR_PAPER_TRADING",
        },
        "youtube_transcript_source_ids": [str(item.id) for item in transcript_sources],
        "knowledge_reference_ids": [item["reference_id"] for item in knowledge],
    }
    details: dict
    if screening.selected_hypothesis_id is None:
        details = {
            "state": "NO_QUALIFYING_STRATEGY",
            "completed_at": datetime.now(UTC).isoformat(),
            "rationale": "No strategy hypothesis passed the preliminary screen after costs",
            "simulation_risk_percent": str(settings.strategy_research_simulation_risk_percent),
            "simulation_risk_authority": "RESEARCH_ONLY",
            "evidence_pack": serialized_pack,
            "holdout_evidence": holdout_evidence,
            "hypotheses": [item.model_dump(mode="json") for item in hypotheses],
            "preliminary_screen": screening.model_dump(mode="json"),
            "strategy_pipeline": {
                **pipeline,
                "stages": {**pipeline["stages"], "preliminary_backtest": "FAILED"},
            },
        }
        artifact = ResearchCycleArchive(settings.research_artifact_root).save_cycle(
            owner_id=owner_id,
            cycle_type="strategy_research",
            cycle_id=run_id,
            occurred_at=datetime.now(UTC),
            details=details,
        )
        async with unit_of_work() as session:
            store = ResourceStore(session)
            run = await store.get("strategy_research_run", run_id, owner_id)
            if run is None:
                raise RuntimeError("strategy research run disappeared")
            draft = await store.get("strategy_draft", UUID(run.data["draft_id"]), owner_id)
            if draft is None:
                raise RuntimeError("strategy draft disappeared")
            for record in (run, draft):
                await store.update(
                    record,
                    {
                        **record.data,
                        **details,
                        "lifecycle_state": "NO_QUALIFYING_STRATEGY",
                        "artifact": {
                            "relative_path": artifact.relative_path,
                            "checksum": artifact.checksum,
                        },
                    },
                    state="NO_QUALIFYING_STRATEGY",
                    event_type="strategy.no_qualifying_hypothesis",
                )
        return details
    proposal = next(
        item for item in hypotheses if item.hypothesis_id == screening.selected_hypothesis_id
    )
    completed_at = datetime.now(UTC)
    details = {
        "origin": origin.value,
        "description": description,
        "simulation_risk_percent": str(settings.strategy_research_simulation_risk_percent),
        "simulation_risk_authority": "RESEARCH_ONLY",
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
        "strategy_pipeline": pipeline,
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
                "simulation_risk_percent": details["simulation_risk_percent"],
                "simulation_risk_authority": details["simulation_risk_authority"],
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
        alternatives = []
        for alternative in retain_family_alternatives(hypotheses, screening):
            if alternative.hypothesis_id == proposal.hypothesis_id:
                continue
            alternative_id = uuid5(
                NAMESPACE_URL, f"strategy-family-proposal:{run_id}:{alternative.hypothesis_id}"
            )
            alternatives.append(str(alternative_id))
            if await store.get("strategy_draft", alternative_id, owner_id):
                continue
            await store.create(
                "strategy_draft",
                owner_id,
                {
                    **draft.data,
                    "proposed_specification": alternative.specification.model_dump(mode="json"),
                    "selected_hypothesis_id": alternative.hypothesis_id,
                    "breakdown": alternative.breakdown,
                    "evidence": alternative.evidence_refs,
                    "rationale": alternative.rationale,
                    "agent_id": alternative.agent_id,
                    "parent_research_draft_id": str(draft.id),
                    "library_candidate": True,
                    "proposal_approval": None,
                },
                record_id=alternative_id,
                state="AWAITING_STRATEGY_APPROVAL",
                event_type="strategy.library_candidate.created",
            )
        details["library_candidate_draft_ids"] = alternatives
        await store.update(
            run,
            {**run.data, "library_candidate_draft_ids": alternatives},
            event_type="strategy.library_candidates.linked",
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
            **await embed_source_data(
                session,
                owner_id,
                build_source_data(
                    name=f"Strategy proposal — {proposal.specification.name}",
                    content=proposal_content,
                    media_type="text/plain",
                    category="strategies",
                    tags=["generated-strategy", "proposal", proposal.specification.family.value],
                    source_date=completed_at.date().isoformat(),
                    source_kind="GENERATED_STRATEGY_PROPOSAL",
                    external_id=str(run_id),
                ),
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


async def _queue_top_pair_strategies(run_id: UUID) -> list[str]:
    async with unit_of_work() as session:
        market_run = await session.get(ResourceRecord, run_id, with_for_update=True)
        if (
            market_run is None
            or market_run.kind != "research_run"
            or market_run.state in {"QUEUED", "RESEARCHING"}
        ):
            return []
        pending = await prepare_strategy_research(session, market_run)
    for strategy_run_id in pending:
        generate_strategy_draft.delay(str(strategy_run_id))
    return [str(item) for item in pending]


@celery_app.task(name="apps.worker.app.tasks.strategies.queue_top_pair_strategies")
def queue_top_pair_strategies(run_id: str) -> list[str]:
    return asyncio.run(_queue_top_pair_strategies(UUID(run_id)))


async def _resume_top_pair_research() -> None:
    async with unit_of_work() as session:
        runs = list(
            (
                await session.scalars(
                    select(ResourceRecord).where(
                        ResourceRecord.kind == "research_run",
                        ResourceRecord.created_at
                        >= datetime.now(UTC)
                        - timedelta(hours=settings.strategy_research_max_market_age_hours),
                        ResourceRecord.state.notin_(["QUEUED", "RESEARCHING", "FAILED"]),
                    )
                )
            ).all()
        )
    for run in runs:
        await _queue_top_pair_strategies(run.id)


@celery_app.task(name="apps.worker.app.tasks.strategies.resume_top_pair_research")
def resume_top_pair_research() -> None:
    asyncio.run(_resume_top_pair_research())


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
        if isinstance(error, ValidationError):
            details["failure_detail"] = "; ".join(
                f"{'.'.join(map(str, item['loc']))}: {item['type']}"
                for item in error.errors(include_input=False)[:5]
            )
        elif isinstance(error, TimeoutError):
            details["failure_detail"] = "agent did not respond before the research deadline"
        elif isinstance(error, InvalidStrategyCondition):
            details["failure_detail"] = str(error)
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
                    "failure_detail": details.get("failure_detail"),
                    "research_artifact": artifact_data,
                },
                state="DEGRADED",
                event_type="strategy.degraded",
            )


@celery_app.task(name="apps.worker.app.tasks.strategies.generate_strategy_draft", time_limit=600)
def generate_strategy_draft(run_id: str) -> dict:
    parsed = UUID(run_id)
    try:
        return asyncio.run(_generate_strategy(parsed))
    except Exception as exc:
        asyncio.run(_mark_strategy_research_failed(parsed, exc))
        raise


async def _run_backtest(run_id: UUID) -> dict:
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id, with_for_update=True)
        if run is None or run.kind != "strategy_backtest":
            raise RuntimeError("strategy backtest run not found")
        if run.state != "QUEUED":
            return {"state": run.state, "run_id": str(run_id)}
        strategy = await session.get(ResourceRecord, UUID(str(run.data["strategy_version_id"])))
        if strategy is None or strategy.kind != "strategy_version":
            raise RuntimeError("strategy version not found")
        basis, connection = await resolve_backtest_basis(session, run.owner_id, strategy)
        if str(run.data["connection_id"]) != basis["historical_connection_id"]:
            raise ValueError("backtest connection differs from the strategy provider binding")
        if run.data["instrument"] != basis["instrument"]:
            raise ValueError("backtest instrument differs from the strategy selection")
        if run.data.get("account_id") and str(run.data["account_id"]) != basis["account_id"]:
            raise ValueError("backtest account differs from the strategy selection")
        specification = StrategySpecification.model_validate(strategy.data["specification"])
        selection = await ResourceStore(session).get(
            "market_selection", UUID(basis["market_selection_id"]), run.owner_id
        )
        execution_contract = (
            selection.data.get("candidate", {}).get("specification", {}) if selection else {}
        )
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
        account_id=UUID(basis["account_id"]),
    )
    timeframe_seconds = TIMEFRAMES[str(run.data["timeframe"])][1]
    evidence_end = datetime.fromisoformat(str(run.data["end_at"]))
    candles = [
        candle
        for candle in candles
        if candle.observed_at + timedelta(seconds=timeframe_seconds) <= evidence_end
    ]
    configuration = BacktestConfiguration(
        initial_equity=Decimal(str(run.data["initial_equity"])),
        spread=Decimal(str(run.data["spread"])),
        commission=Decimal(str(run.data["commission"])),
        slippage=Decimal(str(run.data["slippage"])),
        max_daily_loss=Decimal(str(run.data.get("max_daily_loss", "1000000"))),
        max_total_loss=Decimal(str(run.data.get("max_total_loss", "1000000"))),
        tick_size=Decimal(str(basis["tick_size"])) if basis.get("tick_size") else None,
    )
    calendar, calendar_coverage = (
        historical_calendar(
            ForexFactoryArchive(settings.research_artifact_root),
            owner_id,
            candles[0].observed_at,
            candles[-1].observed_at,
        )
        if candles
        else (None, {"complete": False})
    )
    selection_cut = strategy.data.get("research_selection_cut_at")
    research_seconds = TIMEFRAMES[
        basis.get(
            "research_history_timeframe", basis.get("historical_timeframe", run.data["timeframe"])
        )
    ][1]
    result = PointInTimeBacktester().run(
        specification,
        candles,
        configuration,
        calendar=calendar,
        validation_start_after=datetime.fromisoformat(selection_cut)
        + timedelta(seconds=research_seconds)
        if selection_cut
        else None,
    )
    waiting_for_data = False
    retry_after = None
    if selection_cut:
        closed_selection_cut = datetime.fromisoformat(selection_cut) + timedelta(
            seconds=research_seconds
        )
        unseen_count = sum(c.observed_at > closed_selection_cut for c in candles)
        required_unseen = 60
        waiting_for_data = unseen_count < required_unseen
        result.robustness.update(
            {
                "unseen_candle_count": unseen_count,
                "required_unseen_candles": required_unseen,
                "history_depth_passed": not waiting_for_data,
            }
        )
        result.gates["history_depth"] = not waiting_for_data
        if waiting_for_data:
            result.gates["out_of_sample"] = False
            retry_after = datetime.now(UTC) + timedelta(
                seconds=timeframe_seconds * (required_unseen - unseen_count)
            )
    compiled = compile_strategy(specification)
    execution_validation: dict[str, Any] = (
        {"engine": "NautilusTrader", "status": "WAITING_FOR_UNSEEN_HISTORY", "passed": False}
        if waiting_for_data
        else await asyncio.to_thread(
            validate_execution,
            specification,
            candles,
            configuration,
            timeframe_seconds=timeframe_seconds,
            contract=execution_contract,
            calendar=calendar,
            validation_start_after=closed_selection_cut if selection_cut else None,
        )
    )
    result.gates["event_driven_execution"] = execution_validation["passed"]
    artifact_hash = compiled.artifact_hash
    completed_at = datetime.now(UTC)
    details = {
        **result.model_dump(mode="json"),
        "source": source,
        "artifact_hash": artifact_hash,
        "generated_code": compiled.generated_code,
        "generated_code_language": "python",
        "completed_at": completed_at.isoformat(),
        "calendar_coverage": calendar_coverage,
        "execution_validation": execution_validation,
        "retry_after_at": retry_after.isoformat() if retry_after else None,
        "waiting_reason": "Accumulate at least 60 completed post-selection candles "
        "before independent validation"
        if waiting_for_data
        else None,
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
    state = (
        "WAITING_FOR_DATA"
        if waiting_for_data
        else "PASSED"
        if all(result.gates.values())
        else "FAILED"
    )
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id, with_for_update=True)
        strategy = (
            await session.get(
                ResourceRecord,
                UUID(str(run.data["strategy_version_id"])),
                with_for_update=True,
            )
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
        performance_id = uuid5(NAMESPACE_URL, f"strategy-performance:{run_id}")
        performance_data = {
            "strategy_version_id": str(strategy.id),
            "backtest_id": str(run_id),
            "account_id": basis["account_id"],
            "instrument": basis["instrument"],
            "connection_id": basis["historical_connection_id"],
            "timeframe": run.data["timeframe"],
            "artifact_hash": artifact_hash,
            "family": specification.family.value,
            "execution_validation": {
                key: value
                for key, value in execution_validation.items()
                if key not in {"fills", "closed_positions"}
            },
            "metrics": result.metrics,
            "regime_performance": result.robustness.get("out_of_sample", {}).get(
                "regime_performance", {}
            ),
            "all_history_regime_performance": result.regime_performance,
            "robustness": result.robustness,
            "gates": result.gates,
            "pair_profile": profile_pair(
                candles,
                basis["instrument"],
                calendar=calendar,
                spread=configuration.spread,
                slippage=configuration.slippage,
            ),
            "source": source,
            "completed_at": completed_at.isoformat(),
            "basis": "HISTORICAL_SIMULATION_NOT_LIVE_PERFORMANCE",
        }
        performance_record = await store.get("strategy_performance", performance_id, owner_id)
        if performance_record:
            await store.update(performance_record, performance_data, state=state)
        else:
            await store.create(
                "strategy_performance",
                owner_id,
                performance_data,
                record_id=performance_id,
                state=state,
                event_type="strategy.performance.recorded",
            )
        if strategy.data.get("latest_backtest_id") != str(run_id):
            return {**details, "artifact": artifact_data, "state": state, "superseded": True}
        await store.update(
            strategy,
            {
                **strategy.data,
                "lifecycle_state": StrategyState.VALIDATING,
                "latest_backtest_id": str(run_id),
                "latest_backtest_state": state,
                "validation_retry_after_at": details["retry_after_at"],
                "validation_evidence": {
                    **strategy.data.get("validation_evidence", {}),
                    **result.gates,
                },
                "strategy_pipeline": {
                    **strategy.data.get("strategy_pipeline", {}),
                    "stages": {
                        **strategy.data.get("strategy_pipeline", {}).get("stages", {}),
                        "formal_backtest": state,
                        "validation": state,
                        "paper_trading": "READY" if state == "PASSED" else "BLOCKED",
                    },
                },
            },
            state=StrategyState.VALIDATING,
            event_type="validation_stage.completed",
        )
    return {**details, "artifact": artifact_data, "state": state}


async def _mark_backtest_failed(run_id: UUID, error: Exception) -> None:
    async with unit_of_work() as session:
        run = await session.get(ResourceRecord, run_id, with_for_update=True)
        if run is None or run.kind != "strategy_backtest":
            return
        completed_at = datetime.now(UTC)
        details = {
            "state": "FAILED",
            "completed_at": completed_at.isoformat(),
            "failure": type(error).__name__,
            "failure_detail": (
                f"Historical-data request returned HTTP {error.response.status_code}"
                if isinstance(error, httpx.HTTPStatusError)
                else str(error)[:500]
                if type(error) is ValueError
                else "Backtest execution failed; inspect worker diagnostics"
            ),
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
        store = ResourceStore(session)
        await store.update(
            run,
            {
                **run.data,
                **details,
                "artifact": artifact_data,
            },
            state="FAILED",
            event_type="backtest.failed",
        )
        strategy = await session.get(
            ResourceRecord, UUID(str(run.data["strategy_version_id"])), with_for_update=True
        )
        # Do not let an old delivery overwrite a newer validation attempt.
        if strategy is not None and strategy.data.get("latest_backtest_id") in {None, str(run_id)}:
            evidence = {
                **strategy.data.get("validation_evidence", {}),
                "backtest": False,
                "out_of_sample": False,
                "walk_forward": False,
                "stress": False,
                "policy": False,
            }
            pipeline = {
                **strategy.data.get("strategy_pipeline", {}),
                "stages": {
                    **strategy.data.get("strategy_pipeline", {}).get("stages", {}),
                    "formal_backtest": "FAILED",
                    "validation": "FAILED",
                    "paper_trading": "BLOCKED",
                },
            }
            await store.update(
                strategy,
                {
                    **strategy.data,
                    "lifecycle_state": StrategyState.VALIDATING,
                    "latest_backtest_id": str(run_id),
                    "latest_backtest_state": "FAILED",
                    "validation_evidence": evidence,
                    "strategy_pipeline": pipeline,
                },
                state=StrategyState.VALIDATING,
                event_type="validation_stage.failed",
            )


@celery_app.task(name="apps.worker.app.tasks.strategies.run_strategy_backtest", time_limit=900)
def run_strategy_backtest(run_id: str) -> dict:
    parsed = UUID(run_id)
    try:
        return asyncio.run(_run_backtest(parsed))
    except Exception as exc:
        asyncio.run(_mark_backtest_failed(parsed, exc))
        raise


async def _resume_strategy_backtests() -> list[str]:
    """Recover queued deliveries and workers lost during provider backtests."""
    now = datetime.now(UTC)
    async with unit_of_work() as session:
        runs = list(
            (
                await session.scalars(
                    select(ResourceRecord).where(
                        ResourceRecord.kind == "strategy_backtest",
                        ResourceRecord.state.in_(["QUEUED", "RUNNING"]),
                    )
                )
            ).all()
        )
        store = ResourceStore(session)
        ready = []
        for run in runs:
            if run.state == "RUNNING":
                started_at = run.data.get("started_at")
                if not started_at or now - datetime.fromisoformat(started_at) <= timedelta(
                    minutes=20
                ):
                    continue
                await store.update(
                    run,
                    {**run.data, "recovered_at": now.isoformat()},
                    state="QUEUED",
                    event_type="backtest.delivery_recovered",
                )
            ready.append(str(run.id))
    for run_id in ready:
        run_strategy_backtest.delay(run_id)
    return ready


@celery_app.task(name="apps.worker.app.tasks.strategies.resume_strategy_backtests")
def resume_strategy_backtests() -> list[str]:
    return asyncio.run(_resume_strategy_backtests())


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
