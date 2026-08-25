"""Evidence-bounded AI strategy hypothesis workflow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from modules.research.ports import ResearchAgentGateway
from packages.strategy_sdk.schema import StrategySpecification
from packages.strategy_sdk.taxonomy import StrategyOrigin

SUPPORTED_FEATURES = {
    "open",
    "high",
    "low",
    "close",
    "momentum",
    "moving_average",
    "volatility",
    "volume",
}
SUPPORTED_OPERATORS = {">", ">=", "<", "<=", "=="}

CONDITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "feature": {"type": "string", "enum": sorted(SUPPORTED_FEATURES)},
        "operator": {"type": "string", "enum": sorted(SUPPORTED_OPERATORS)},
        "value": {"type": "string"},
    },
    "required": ["feature", "operator", "value"],
    "additionalProperties": False,
}

STRATEGY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "family": {
            "type": "string",
            "enum": ["TREND", "MEAN_REVERSION", "BREAKOUT", "LIQUIDITY", "EVENT"],
        },
        "horizon": {"type": "string", "enum": ["INTRADAY", "SWING", "POSITION"]},
        "instruments": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "regimes": {"type": "array", "items": {"type": "string"}},
        "data_dependencies": {"type": "array", "items": {"type": "string"}},
        "entry": {"type": "array", "items": CONDITION_SCHEMA, "minItems": 1},
        "confirmations": {"type": "array", "items": CONDITION_SCHEMA},
        "filters": {"type": "array", "items": CONDITION_SCHEMA},
        "exit": {"type": "array", "items": CONDITION_SCHEMA, "minItems": 1},
        "invalidation": {"type": "array", "items": CONDITION_SCHEMA},
        "stop_loss": CONDITION_SCHEMA,
        "take_profit": {"type": "array", "items": CONDITION_SCHEMA},
        "position_management": {
            "type": "object",
            "properties": {
                "move_to_break_even": {"type": "boolean"},
                "trailing_stop": {"type": "boolean"},
                "partial_take_profit": {"type": "boolean"},
            },
            "required": ["move_to_break_even", "trailing_stop", "partial_take_profit"],
            "additionalProperties": False,
        },
        "sessions": {"type": "array", "items": {"type": "string"}},
        "event_rules": {"type": "array", "items": {"type": "string"}},
        "risk_per_trade": {"type": "string"},
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "required": [
        "name",
        "family",
        "horizon",
        "instruments",
        "regimes",
        "data_dependencies",
        "entry",
        "confirmations",
        "filters",
        "exit",
        "invalidation",
        "stop_loss",
        "take_profit",
        "position_management",
        "sessions",
        "event_rules",
        "risk_per_trade",
        "parameters",
    ],
    "additionalProperties": False,
}

STRATEGY_GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "hypothesis_id": {"type": "string"},
                    "strategy": STRATEGY_SCHEMA,
                    "rationale": {"type": "string"},
                    "breakdown": {"type": "array", "items": {"type": "string"}, "minItems": 3},
                    "evidence_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
                "required": [
                    "hypothesis_id",
                    "strategy",
                    "rationale",
                    "breakdown",
                    "evidence_refs",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hypotheses"],
    "additionalProperties": False,
}


class StrategyHypothesis(BaseModel):
    hypothesis_id: str
    specification: StrategySpecification
    rationale: str = Field(min_length=1)
    breakdown: list[str] = Field(min_length=3)
    evidence_refs: list[str] = Field(min_length=1)
    agent_id: str


class StrategyGenerationWorkflow:
    def __init__(self, agents: ResearchAgentGateway) -> None:
        self.agents = agents

    async def generate_hypotheses(
        self,
        origin: StrategyOrigin,
        evidence_pack: dict[str, Any],
        description: str | None = None,
    ) -> list[StrategyHypothesis]:
        prompt = (description or "").strip()
        if origin == StrategyOrigin.AI_ASSISTED and not prompt:
            raise ValueError("AI-assisted strategy generation requires a human description")
        instrument = str(evidence_pack.get("instrument") or "")
        selection_id = str(evidence_pack.get("selection_id") or "")
        references = {
            str(item.get("id"))
            for item in evidence_pack.get("references", [])
            if isinstance(item, dict) and item.get("id")
        }
        if not instrument or not selection_id or not references:
            raise ValueError("an immutable approved-market evidence pack is required")
        role = (
            "strategy_researcher"
            if origin == StrategyOrigin.AI_GENERATED
            else "strategy_assistant"
        )
        response = await self.agents.invoke(
            role,
            {
                "origin": origin.value,
                "description": prompt or "Develop distinct grounded strategy hypotheses",
                "evidence_pack": evidence_pack,
                "requirements": {
                    "hypothesis_count": 3,
                    "approved_instrument_only": instrument,
                    "cite_only_evidence_reference_ids": sorted(references),
                    "complete_deterministic_rules": True,
                    "supported_features": sorted(SUPPORTED_FEATURES),
                    "supported_operators": sorted(SUPPORTED_OPERATORS),
                    "human_approval_required": True,
                    "do_not_select_winner": True,
                },
            },
            STRATEGY_GENERATION_SCHEMA,
        )
        raw_hypotheses = response.get("hypotheses")
        if not isinstance(raw_hypotheses, list) or len(raw_hypotheses) != 3:
            raise ValueError("strategy agent must return exactly three hypotheses")
        hypotheses: list[StrategyHypothesis] = []
        seen_ids: set[str] = set()
        for raw in raw_hypotheses:
            if not isinstance(raw, dict) or not isinstance(raw.get("strategy"), dict):
                raise ValueError("strategy agent returned an invalid hypothesis")
            identifier = str(raw.get("hypothesis_id") or "").strip()
            if not identifier or identifier in seen_ids:
                raise ValueError("strategy hypothesis identifiers must be unique")
            seen_ids.add(identifier)
            evidence_refs = [str(item) for item in raw.get("evidence_refs", [])]
            unknown = set(evidence_refs) - references
            if unknown:
                raise ValueError(f"unknown evidence reference: {sorted(unknown)[0]}")
            specification = StrategySpecification.model_validate(
                {
                    **raw["strategy"],
                    "origin": origin.value,
                    "evaluator_version": "strategy-evaluator-v1",
                }
            )
            if specification.instruments != [instrument]:
                raise ValueError("strategy hypothesis must use only the approved instrument")
            conditions = [
                *specification.entry,
                *specification.confirmations,
                *specification.filters,
                *specification.exit,
                *specification.invalidation,
                specification.stop_loss,
                *specification.take_profit,
            ]
            if any(
                item.feature not in SUPPORTED_FEATURES or item.operator not in SUPPORTED_OPERATORS
                for item in conditions
            ):
                raise ValueError("strategy hypothesis uses an unsupported evaluator rule")
            hypotheses.append(
                StrategyHypothesis(
                    hypothesis_id=identifier,
                    specification=specification,
                    rationale=str(raw.get("rationale") or ""),
                    breakdown=raw.get("breakdown", []),
                    evidence_refs=evidence_refs,
                    agent_id=role,
                )
            )
        return hypotheses
