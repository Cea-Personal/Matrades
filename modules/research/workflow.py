"""Autonomous discovery, ranking, specialist review, and criticism workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modules.research.features import fingerprint
from modules.research.models import (
    AgentReview,
    MarketCategory,
    ResearchCandidate,
    ResearchCycleResult,
)
from modules.research.ports import ResearchAgentGateway, ResearchDataProvider

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
AGENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string"},
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
                    candidate.agent_evidence.extend(
                        evidence
                    )
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
        state = "MARKETS_PENDING_APPROVAL" if not unique_missing and not degraded else "DEGRADED"
        return ResearchCycleResult(
            state=state,
            candidates=selected,
            missing_categories=unique_missing,
            degraded_reasons=list(dict.fromkeys(degraded)),
            agent_reviews=reviews,
            completed_at=datetime.now(UTC),
        )
