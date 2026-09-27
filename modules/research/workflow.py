"""Autonomous discovery, ranking, specialist review, and criticism workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modules.research.features import IneligibleResearchEvidence, fingerprint, typed_fingerprint
from modules.research.matrix import aggregate_status
from modules.research.models import (
    AgentReview,
    MarketCategory,
    ResearchCandidate,
    ResearchCycleResult,
    ResearchLaneResult,
    TypedResearchCandidate,
    TypedResearchRun,
    TypedResearchSnapshot,
)
from modules.research.ports import ResearchAgentGateway, ResearchDataProvider
from packages.shared.domain_types import AssetClass, LaneStatus

ANALYST_ROLES = (
    "technical_analyst",
    "fundamental_analyst",
    "sentiment_analyst",
    "regime_analyst",
)
CATEGORY_ROLES = {
    MarketCategory.FOREX: "forex_research",
    MarketCategory.METAL: "metals_research",
    MarketCategory.CRYPTO: "crypto_research",
}
ASSET_CLASS_ROLES = {
    AssetClass.FOREX: "forex_research",
    AssetClass.METALS: "metals_research",
    AssetClass.CRYPTOCURRENCY: "crypto_research",
    AssetClass.STOCKS: "stocks_research",
}
AGENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "REASSESS"]},
        "score_adjustments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string"},
                    "adjustment": {"type": "number", "minimum": -10, "maximum": 10},
                },
                "required": ["instrument", "adjustment"],
                "additionalProperties": False,
            },
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "score_adjustments", "evidence"],
    "additionalProperties": False,
}


def _bounded_adjustments(response: dict[str, Any]) -> dict[str, float]:
    raw = response.get("score_adjustments", {})
    if isinstance(raw, list):
        raw = {
            str(item.get("instrument")): item.get("adjustment")
            for item in raw
            if isinstance(item, dict) and item.get("instrument")
        }
    if not isinstance(raw, dict):
        return {}
    adjustments: dict[str, float] = {}
    for instrument, value in raw.items():
        if isinstance(instrument, str) and isinstance(value, (int, float)):
            adjustments[instrument] = max(-10.0, min(10.0, float(value)))
    return adjustments


def _review_decision(response: dict[str, Any]) -> tuple[str, str]:
    """Normalize model prose to the fail-closed verdict vocabulary without discarding it."""
    raw = str(response.get("decision", "REASSESS")).strip() or "REASSESS"
    return ("PASS" if raw.upper() == "PASS" else "REASSESS", raw)


def _provider_failure_detail(exc: Exception) -> str | None:
    """Expose safe domain diagnostics without persisting URLs or credential-bearing errors."""
    if type(exc).__name__ != "ResearchDataUnavailable":
        return None
    return str(exc).strip()[:500] or None


def _agent_failure_detail(exc: Exception) -> str:
    """Keep the underlying runtime diagnostic in the typed lane result."""
    detail = str(exc).strip()
    return f"{type(exc).__name__}: {detail}"[:500]


def _market_research_review_contract(role: str) -> dict[str, Any]:
    """Keep analytical selection separate from later broker execution authority."""
    return {
        "stage": "MARKET_CANDIDATE_RESEARCH",
        "session_policy": (
            "Deterministic eligibility gates have already checked timestamp validity. "
            "A measured fingerprint marked WEEKEND_CLOSED permits bounded last-session "
            "history for research only. Do not request REASSESS solely because those "
            "quotes/candles predate the weekend; no actionable entry is permitted until "
            "the market reopens and fresh evidence is obtained."
        ),
        "review_role": role,
        "decision_semantics": {
            "PASS": "Evidence is adequate for this candidate to continue research ranking.",
            "REASSESS": (
                "Core market evidence is stale, corrupt, contradictory, or otherwise "
                "insufficient to support research ranking."
            ),
        },
        "cfd_proxy_policy": (
            "A non-executable underlying-market proxy is expected for CFD research. "
            "Do not return REASSESS solely because executable=false or because later "
            "MT5 broker validation is required."
        ),
        "optional_context_policy": (
            "Missing macro, sentiment, or event-risk context must be disclosed and must "
            "receive a zero adjustment; it is not by itself a reason to block a candidate "
            "whose core price evidence is fresh and usable."
        ),
        "execution_boundary": (
            "PASS advances research only. It never authorizes a strategy, risk decision, "
            "broker symbol, order, or trade. MT5 validation remains mandatory later."
        ),
    }


class AutonomousResearchWorkflow:
    def __init__(
        self,
        provider: ResearchDataProvider,
        agents: ResearchAgentGateway,
    ) -> None:
        self.provider = provider
        self.agents = agents

    async def run(self, categories: list[MarketCategory]) -> ResearchCycleResult:
        by_category: dict[MarketCategory, list[ResearchCandidate]] = {}
        degraded: list[str] = []
        missing: list[MarketCategory] = []
        reviews: list[AgentReview] = []

        for category in categories:
            try:
                snapshots = await self.provider.gather(category)
            except Exception as exc:  # provider boundary must degrade safely
                snapshots = []
                degraded.append(f"{category.value}: provider unavailable ({type(exc).__name__})")
            if not snapshots:
                missing.append(category)
                degraded.append(f"{category.value}: no fresh provider observations")
                continue
            candidates: list[ResearchCandidate] = []
            for snapshot in snapshots:
                market_fingerprint, score, evidence = fingerprint(snapshot)
                candidates.append(
                    ResearchCandidate(
                        instrument=snapshot.instrument,
                        category=category,
                        score=score,
                        fingerprint=market_fingerprint,
                        evidence=evidence,
                    )
                )
            by_category[category] = candidates

        flattened = [candidate for group in by_category.values() for candidate in group]
        analyst_evidence: list[str] = []
        for role in ANALYST_ROLES if flattened else ():
            try:
                response = await self.agents.invoke(
                    role,
                    {"candidates": [item.model_dump(mode="json") for item in flattened]},
                    AGENT_OUTPUT_SCHEMA,
                )
                evidence = [str(item) for item in response.get("evidence", [])]
                if str(response.get("decision", "REASSESS")).upper() != "PASS":
                    degraded.append(f"{role}: requested reassessment")
                    reviews.append(
                        AgentReview(logical_id=role, status="REASSESS", evidence=evidence)
                    )
                    continue
                adjustments = _bounded_adjustments(response)
                analyst_evidence.extend(evidence)
                reviews.append(AgentReview(logical_id=role, status="PASS", evidence=evidence))
                for candidate in flattened:
                    candidate.score = max(
                        0.0,
                        min(100.0, candidate.score + adjustments.get(candidate.instrument, 0.0)),
                    )
            except Exception as exc:
                degraded.append(f"{role}: unavailable ({type(exc).__name__})")
                reviews.append(AgentReview(logical_id=role, status="DEGRADED"))

        selected: list[ResearchCandidate] = []
        for category, candidates in by_category.items():
            role = CATEGORY_ROLES[category]
            try:
                response = await self.agents.invoke(
                    role,
                    {"candidates": [item.model_dump(mode="json") for item in candidates]},
                    AGENT_OUTPUT_SCHEMA,
                )
                evidence = [str(item) for item in response.get("evidence", [])]
                if str(response.get("decision", "REASSESS")).upper() != "PASS":
                    missing.append(category)
                    degraded.append(f"{role}: requested reassessment")
                    reviews.append(
                        AgentReview(logical_id=role, status="REASSESS", evidence=evidence)
                    )
                    continue
                adjustments = _bounded_adjustments(response)
                reviews.append(AgentReview(logical_id=role, status="PASS", evidence=evidence))
                for candidate in candidates:
                    candidate.score = max(
                        0.0,
                        min(100.0, candidate.score + adjustments.get(candidate.instrument, 0.0)),
                    )
                    candidate.agent_evidence.extend(analyst_evidence)
                    candidate.agent_evidence.extend(evidence)
            except Exception as exc:
                missing.append(category)
                degraded.append(f"{role}: unavailable ({type(exc).__name__})")
                reviews.append(AgentReview(logical_id=role, status="DEGRADED"))
                continue

            best = sorted(candidates, key=lambda item: (-item.score, item.instrument))[0]
            try:
                criticism = await self.agents.invoke(
                    "critic",
                    {"candidates": [best.model_dump(mode="json")]},
                    AGENT_OUTPUT_SCHEMA,
                )
            except Exception as exc:
                missing.append(category)
                degraded.append(f"{category.value}: critic unavailable ({type(exc).__name__})")
                reviews.append(AgentReview(logical_id="critic", status="DEGRADED"))
                continue
            criticism_evidence = [str(item) for item in criticism.get("evidence", [])]
            if str(criticism.get("decision", "REASSESS")).upper() != "PASS":
                missing.append(category)
                degraded.append(f"{category.value}: critic requested reassessment")
                reviews.append(
                    AgentReview(
                        logical_id="critic",
                        status="REASSESS",
                        evidence=criticism_evidence,
                    )
                )
                continue
            reviews.append(
                AgentReview(logical_id="critic", status="PASS", evidence=criticism_evidence)
            )
            best.agent_evidence.extend(criticism_evidence)
            best.rank = 1
            best.score = round(best.score, 4)
            selected.append(best)

        unique_missing = list(dict.fromkeys(missing))
        state = "COMPLETED" if not unique_missing and not degraded else "DEGRADED"
        return ResearchCycleResult(
            state=state,
            candidates=selected,
            missing_categories=unique_missing,
            degraded_reasons=list(dict.fromkeys(degraded)),
            agent_reviews=reviews,
            completed_at=datetime.now(UTC),
        )

    async def run_matrix(self, run: TypedResearchRun) -> TypedResearchRun:
        """Run each lane independently and always persist one terminal result per lane.

        Providers may implement ``gather_lane``; a missing method is an explicit unconfigured
        outcome rather than an implicit fallback to another instrument type.
        """
        results: list[ResearchLaneResult] = []
        for lane in run.requested_lanes:
            try:
                gather_lane = self.provider.gather_lane
                snapshots = await gather_lane(lane)
            except AttributeError:
                snapshots = []
                status = LaneStatus.NOT_CONFIGURED
                results.append(
                    ResearchLaneResult(
                        run_id=run.id,
                        lane=lane,
                        status=status,
                        reason_code="PROVIDER_LANE_CAPABILITY_MISSING",
                        completed_at=datetime.now(UTC),
                    )
                )
                continue
            except Exception as exc:
                results.append(
                    ResearchLaneResult(
                        run_id=run.id,
                        lane=lane,
                        status=getattr(exc, "lane_status", LaneStatus.UNAVAILABLE),
                        reason_code=f"PROVIDER_ERROR:{type(exc).__name__}",
                        failure_detail=_provider_failure_detail(exc),
                        completed_at=datetime.now(UTC),
                    )
                )
                continue
            typed = [TypedResearchSnapshot.model_validate(item) for item in snapshots]
            observed_candidates = [item.listing.symbol for item in typed]
            source_cut_refs = list(dict.fromkeys(item.source_cut_id for item in typed))
            measured = {}
            rejected = []
            eligible = []
            for item in typed:
                try:
                    measured[item.listing.symbol] = typed_fingerprint(item)
                    eligible.append(item)
                except IneligibleResearchEvidence as exc:
                    rejected.append(f"{item.listing.symbol}:{exc}")
            typed = eligible
            if not typed:
                results.append(
                    ResearchLaneResult(
                        run_id=run.id,
                        lane=lane,
                        status=LaneStatus.NO_TRADE,
                        reason_code="NO_ELIGIBLE_CANDIDATE",
                        exclusions=rejected,
                        observed_candidates=observed_candidates,
                        source_cut_refs=source_cut_refs,
                        completed_at=datetime.now(UTC),
                    )
                )
                continue
            reviews: list[AgentReview] = []
            base_scores = {symbol: values[1] for symbol, values in measured.items()}
            adjusted_scores = dict(base_scores)
            analyst_failed = False
            for role in (*ANALYST_ROLES, ASSET_CLASS_ROLES[lane.asset_class]):
                try:
                    response = await self.agents.invoke(
                        role,
                        {
                            "lane": lane.model_dump(mode="json"),
                            "candidates": [item.model_dump(mode="json") for item in typed],
                            "source_cut_refs": source_cut_refs,
                            "measured_criteria": {
                                symbol: values[0].model_dump(mode="json")
                                for symbol, values in measured.items()
                            },
                            "review_contract": _market_research_review_contract(role),
                        },
                        AGENT_OUTPUT_SCHEMA,
                    )
                    evidence = [str(item) for item in response.get("evidence", [])]
                    score_adjustments = _bounded_adjustments(response)
                    review_status, raw_decision = _review_decision(response)
                    reviews.append(
                        AgentReview(
                            logical_id=role,
                            status=review_status,
                            raw_decision=raw_decision,
                            evidence=evidence,
                            score_adjustments=score_adjustments,
                        )
                    )
                    if review_status != "PASS":
                        analyst_failed = True
                        break
                    for symbol, adjustment in score_adjustments.items():
                        if symbol in adjusted_scores:
                            adjusted_scores[symbol] = max(
                                max(0.0, base_scores[symbol] - 15.0),
                                min(
                                    100.0,
                                    base_scores[symbol] + 15.0,
                                    adjusted_scores[symbol] + adjustment,
                                ),
                            )
                except Exception as exc:
                    reviews.append(
                        AgentReview(
                            logical_id=role,
                            status="UNAVAILABLE",
                            evidence=[f"Agent invocation failed: {_agent_failure_detail(exc)}"],
                        )
                    )
                    results.append(
                        ResearchLaneResult(
                            run_id=run.id,
                            lane=lane,
                            status=LaneStatus.UNAVAILABLE,
                            reason_code=f"AGENT_ERROR:{role}:{type(exc).__name__}",
                            failure_detail=_agent_failure_detail(exc),
                            exclusions=[f"agent={role}"],
                            source_cut_refs=source_cut_refs,
                            observed_candidates=observed_candidates,
                            agent_reviews=reviews,
                            completed_at=datetime.now(UTC),
                        )
                    )
                    analyst_failed = True
                    break
            if analyst_failed:
                if not results or results[-1].lane != lane:
                    results.append(
                        ResearchLaneResult(
                            run_id=run.id,
                            lane=lane,
                            status=LaneStatus.NO_TRADE,
                            reason_code="ANALYST_REASSESS",
                            exclusions=[
                                review.logical_id for review in reviews if review.status != "PASS"
                            ],
                            source_cut_refs=source_cut_refs,
                            observed_candidates=observed_candidates,
                            agent_reviews=reviews,
                            completed_at=datetime.now(UTC),
                        )
                    )
                continue
            ranked_snapshots = sorted(
                typed,
                key=lambda item: (-adjusted_scores[item.listing.symbol], item.listing.symbol),
            )
            try:
                response = await self.agents.invoke(
                    "critic",
                    {
                        "lane": lane.model_dump(mode="json"),
                        "candidates": [item.model_dump(mode="json") for item in ranked_snapshots],
                        "source_cut_refs": source_cut_refs,
                        "measured_criteria": {
                            symbol: values[0].model_dump(mode="json")
                            for symbol, values in measured.items()
                        },
                        "review_contract": _market_research_review_contract("critic"),
                    },
                    AGENT_OUTPUT_SCHEMA,
                )
                critic_status, critic_raw_decision = _review_decision(response)
                reviews.append(
                    AgentReview(
                        logical_id="critic",
                        status=critic_status,
                        raw_decision=critic_raw_decision,
                        evidence=[str(item) for item in response.get("evidence", [])],
                        score_adjustments=_bounded_adjustments(response),
                    )
                )
                if critic_status != "PASS":
                    results.append(
                        ResearchLaneResult(
                            run_id=run.id,
                            lane=lane,
                            status=LaneStatus.NO_TRADE,
                            reason_code="CRITIC_REASSESS",
                            exclusions=[item.listing.symbol for item in ranked_snapshots],
                            source_cut_refs=source_cut_refs,
                            observed_candidates=observed_candidates,
                            agent_reviews=reviews,
                            completed_at=datetime.now(UTC),
                        )
                    )
                    continue
                for symbol, adjustment in _bounded_adjustments(response).items():
                    if symbol in adjusted_scores:
                        adjusted_scores[symbol] = max(
                            max(0.0, base_scores[symbol] - 15.0),
                            min(
                                100.0,
                                base_scores[symbol] + 15.0,
                                adjusted_scores[symbol] + adjustment,
                            ),
                        )
                ranked_snapshots = sorted(
                    typed,
                    key=lambda item: (-adjusted_scores[item.listing.symbol], item.listing.symbol),
                )
            except Exception as exc:
                reviews.append(
                    AgentReview(
                        logical_id="critic",
                        status="UNAVAILABLE",
                        evidence=[f"Agent invocation failed: {type(exc).__name__}"],
                    )
                )
                results.append(
                    ResearchLaneResult(
                        run_id=run.id,
                        lane=lane,
                        status=LaneStatus.UNAVAILABLE,
                        reason_code=f"CRITIC_ERROR:{type(exc).__name__}",
                        source_cut_refs=source_cut_refs,
                        observed_candidates=observed_candidates,
                        agent_reviews=reviews,
                        completed_at=datetime.now(UTC),
                    )
                )
                continue
            candidates: list[TypedResearchCandidate] = []
            for rank, snapshot in enumerate(ranked_snapshots, start=1):
                market_fingerprint, _, measured_evidence = measured[snapshot.listing.symbol]
                candidates.append(
                    TypedResearchCandidate(
                        lane=lane,
                        listing=snapshot.listing,
                        specification=snapshot.specification,
                        rank=rank,
                        score=round(adjusted_scores[snapshot.listing.symbol], 4),
                        fingerprint=market_fingerprint,
                        evidence=[f"source_cut={snapshot.source_cut_id}"]
                        + measured_evidence
                        + [evidence for review in reviews for evidence in review.evidence],
                    )
                )
            results.append(
                ResearchLaneResult(
                    run_id=run.id,
                    lane=lane,
                    status=LaneStatus.READY,
                    candidate=candidates[0],
                    ranked_candidates=candidates,
                    exclusions=rejected + [item.listing.symbol for item in ranked_snapshots[1:]],
                    source_cut_refs=source_cut_refs,
                    observed_candidates=observed_candidates,
                    agent_reviews=reviews,
                    completed_at=datetime.now(UTC),
                )
            )
        # Prefer distinct underlyings / forex currency exposures among lane winners.
        # This is an exposure heuristic, not return correlation or account-position risk.
        selected_underlyings = set()
        currency_exposures = set()
        ready = sorted(
            (item for item in results if item.status == LaneStatus.READY),
            key=lambda item: (-item.candidate.score, item.lane.as_string()),
        )
        for result in ready:
            for candidate in result.ranked_candidates:
                symbol = candidate.listing.symbol.upper().replace("/", "")
                direction = candidate.fingerprint.criteria.get("direction") or 0
                exposures = set()
                if candidate.lane.asset_class == AssetClass.FOREX and len(symbol) == 6:
                    exposures = {(symbol[:3], direction), (symbol[3:], -direction)}
                duplicate = candidate.listing.underlying_id in selected_underlyings
                overlap = len(exposures & currency_exposures)
                penalty = min(15.0, 10.0 * duplicate + 5.0 * overlap)
                candidate.score = round(max(0.0, candidate.score - penalty), 4)
                candidate.fingerprint.criteria["diversification_penalty"] = penalty
                candidate.evidence.append(
                    f"Lane-winner exposure overlap penalty={penalty}; "
                    "not a portfolio correlation or position-risk assessment"
                )
            result.ranked_candidates.sort(key=lambda item: (-item.score, item.listing.symbol))
            for rank, candidate in enumerate(result.ranked_candidates, start=1):
                candidate.rank = rank
            result.candidate = result.ranked_candidates[0]
            winner = result.candidate
            selected_underlyings.add(winner.listing.underlying_id)
            symbol = winner.listing.symbol.upper().replace("/", "")
            direction = winner.fingerprint.criteria.get("direction") or 0
            if winner.lane.asset_class == AssetClass.FOREX and len(symbol) == 6:
                currency_exposures.update({(symbol[:3], direction), (symbol[3:], -direction)})
            result.exclusions = [entry for entry in result.exclusions if ":" in entry] + [
                item.listing.symbol for item in result.ranked_candidates[1:]
            ]
        return run.model_copy(update={"lane_results": results, "state": aggregate_status(results)})
