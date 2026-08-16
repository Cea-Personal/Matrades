from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.market_data.model import Instrument
from traderx.market_research.events import (
    CATEGORY_BLOCKED,
    COORDINATED_COMPLETED,
    emit_market_research_fact,
)
from traderx.market_research.model import (
    CandidateAssessment,
    CoordinatedMarketResearchRun,
    MarketResearchOccurrence,
    MarketResearchRun,
)

CATEGORIES = ("COMMODITY", "CRYPTO", "FOREX")


def create_coordinated_run(
    database: Session,
    *,
    account_id: UUID,
    trigger: str,
    methodology_version: str,
    source_catalogue_revision: str,
    freshness_policy_manifest: dict[str, str],
    retry_policy_manifest: dict[str, str],
    now: datetime,
    llm_pin: dict[str, object] | None = None,
    occurrence: MarketResearchOccurrence | None = None,
) -> CoordinatedMarketResearchRun:
    if occurrence is not None:
        existing = database.scalar(
            select(CoordinatedMarketResearchRun).where(
                CoordinatedMarketResearchRun.occurrence_id == occurrence.id
            )
        )
        if existing is not None:
            return existing
    pin = llm_pin or {}
    parent = CoordinatedMarketResearchRun(
        account_id=account_id,
        occurrence_id=occurrence.id if occurrence else None,
        trigger=trigger,
        state="QUEUED",
        expected_category_count=3,
        methodology_version=methodology_version,
        source_catalogue_revision=source_catalogue_revision,
        freshness_policy_manifest=dict(freshness_policy_manifest),
        retry_policy_manifest=dict(retry_policy_manifest),
        llm_integration_id=_uuid_or_none(pin.get("llm_integration_id")),
        llm_provider_key=_text_or_none(pin.get("provider_key")),
        exact_model_id=_text_or_none(pin.get("exact_model_id")),
        llm_catalogue_revision=_text_or_none(pin.get("catalogue_revision")),
        llm_adapter_revision=_text_or_none(pin.get("adapter_revision")),
        prompt_template_version=_text_or_none(pin.get("prompt_template_version")),
        output_schema_version=_text_or_none(pin.get("output_schema_version")),
        inference_policy_version=_text_or_none(pin.get("inference_policy_version")),
        created_at=now,
    )
    database.add(parent)
    database.flush()
    common_pins: dict[str, object] = {
        "source_catalogue_revision": source_catalogue_revision,
        "freshness_policy_manifest": dict(freshness_policy_manifest),
        "retry_policy_manifest": dict(retry_policy_manifest),
        "llm": json.loads(json.dumps(pin, sort_keys=True, default=str)),
    }
    for category in CATEGORIES:
        manifest = {
            "coordinated_run_id": str(parent.id),
            "category": category,
            "methodology_version": methodology_version,
            "policy_pins": common_pins,
        }
        database.add(
            MarketResearchRun(
                coordinated_run_id=parent.id,
                category=category,
                method_version=methodology_version,
                input_manifest_hash=_stable_hash(manifest),
                state="QUEUED",
                source_manifest={},
                fallback_path=[],
                block_reasons=[],
                policy_pins=common_pins,
                created_at=now,
            )
        )
    if occurrence is not None:
        occurrence.coordinated_run_id = parent.id
    database.flush()
    return parent


def record_category_outcome(
    database: Session,
    run: MarketResearchRun,
    *,
    outcome: str,
    completed_at: datetime,
    block_reasons: list[str] | None = None,
    correlation_id: str = "market-research-worker",
) -> None:
    run.state = "BLOCKED" if outcome == "BLOCKED" else "COMPLETED"
    run.block_reasons = list(block_reasons or [])
    run.completed_at = completed_at
    parent = (
        database.get(CoordinatedMarketResearchRun, run.coordinated_run_id)
        if run.coordinated_run_id
        else None
    )
    if parent is not None:
        if outcome == "BLOCKED":
            emit_market_research_fact(
                database,
                aggregate_type="market_research_run",
                aggregate_id=run.id,
                aggregate_version=run.version,
                event_type=CATEGORY_BLOCKED,
                data={
                    "category": run.category,
                    "block_reasons": list(block_reasons or []),
                    "active_assignment_changed": False,
                },
                now=completed_at,
                correlation_id=correlation_id,
            )
        children = list(
            database.scalars(
                select(MarketResearchRun).where(
                    MarketResearchRun.coordinated_run_id == parent.id
                )
            )
        )
        if all(child.state in {"COMPLETED", "BLOCKED", "FAILED"} for child in children):
            blocked = sum(child.state != "COMPLETED" for child in children)
            parent.state = "COMPLETED" if blocked == 0 else "PARTIAL"
            parent.completed_at = completed_at
            parent.outcome_summary = {
                "completed": len(children) - blocked,
                "blocked_or_failed": blocked,
            }
            emit_market_research_fact(
                database,
                aggregate_type="coordinated_market_research_run",
                aggregate_id=parent.id,
                aggregate_version=parent.version,
                event_type=COORDINATED_COMPLETED,
                data={
                    "state": parent.state,
                    "category_outcomes": {
                        child.category: child.state for child in children
                    },
                    "source_catalogue_revision": parent.source_catalogue_revision,
                    "exact_model_id": parent.exact_model_id,
                    "active_assignments_changed": False,
                },
                now=completed_at,
                correlation_id=correlation_id,
            )
    database.flush()


def coordinated_report(database: Session, run_id: UUID) -> dict[str, object]:
    parent = database.get(CoordinatedMarketResearchRun, run_id)
    if parent is None:
        raise ValueError("coordinated market research run does not exist")
    children = list(
        database.scalars(
            select(MarketResearchRun)
            .where(MarketResearchRun.coordinated_run_id == parent.id)
            .order_by(MarketResearchRun.category)
        )
    )
    categories: list[dict[str, object]] = []
    for child in children:
        assessment_rows = database.execute(
            select(CandidateAssessment, Instrument)
            .join(Instrument, Instrument.id == CandidateAssessment.instrument_id)
            .where(CandidateAssessment.research_run_id == child.id)
            .order_by(CandidateAssessment.rank, Instrument.symbol)
        ).all()
        categories.append({
            "run_id": str(child.id),
            "category": child.category,
            "state": child.state,
            "outcome": (
                "BLOCKED"
                if child.state in {"BLOCKED", "FAILED"}
                else "RECOMMENDED"
                if child.state == "COMPLETED"
                else "PENDING"
            ),
            "block_reasons": child.block_reasons,
            "source_manifest": child.source_manifest,
            "fallback_path": child.fallback_path,
            "deterministic_result_hash": child.deterministic_result_hash,
            "llm_analysis": {
                "state": child.llm_analysis_state,
                "authoritative": False,
            },
            "activation_state": "REQUIRES_SEPARATE_HUMAN_CONFIRMATION",
            "candidates": [
                {
                    "id": str(assessment.id),
                    "symbol": instrument.symbol,
                    "display_name": instrument.display_name,
                    "eligible": assessment.eligible,
                    "score": str(assessment.score) if assessment.score is not None else None,
                    "rank": assessment.rank,
                    "confidence": str(assessment.confidence),
                    "exclusions": assessment.gate_evidence.get("reason_codes", []),
                    "components": assessment.components,
                }
                for assessment, instrument in assessment_rows
            ],
        })
    return {
        "id": str(parent.id),
        "state": parent.state,
        "trigger": parent.trigger,
        "created_at": parent.created_at.isoformat(),
        "completed_at": parent.completed_at.isoformat() if parent.completed_at else None,
        "methodology_version": parent.methodology_version,
        "source_catalogue_revision": parent.source_catalogue_revision,
        "exact_model_id": parent.exact_model_id,
        "categories": categories,
        "ranking_is_not_activation": True,
        "active_assignments_changed": False,
    }


def _stable_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _text_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _uuid_or_none(value: object) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))
