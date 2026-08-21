from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
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
    LlmAnalysisAttempt,
    MarketResearchOccurrence,
    MarketResearchRun,
)
from traderx.notifications.router import notify_market_research_owners

CATEGORIES = ("COMMODITY", "CRYPTO", "FOREX")


@dataclass(frozen=True, slots=True)
class CategoryRunClaim:
    run_id: UUID
    lease_token: str
    attempt_count: int


def claim_category_run(
    database: Session,
    run_id: UUID,
    *,
    now: datetime,
    lease_owner: str,
    lease_token: str,
    lease_duration: timedelta = timedelta(minutes=15),
) -> CategoryRunClaim | None:
    """Atomically claim a category run or fence an at-least-once redelivery."""

    run = database.scalar(
        select(MarketResearchRun)
        .where(MarketResearchRun.id == run_id)
        .with_for_update(skip_locked=True)
    )
    if run is None or run.state in {"COMPLETED", "BLOCKED", "FAILED"}:
        return None
    lease_expires_at = run.lease_expires_at
    if lease_expires_at is not None and lease_expires_at.tzinfo is None:
        lease_expires_at = lease_expires_at.replace(tzinfo=now.tzinfo)
    if run.state == "RUNNING" and lease_expires_at is not None and lease_expires_at > now:
        return None
    run.state = "RUNNING"
    run.lease_owner = lease_owner
    run.lease_token = lease_token
    run.lease_expires_at = now + lease_duration
    run.attempt_count += 1
    run.current_error = None
    database.flush()
    return CategoryRunClaim(run.id, lease_token, run.attempt_count)


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
        research_brief=_text_or_none(pin.get("research_brief")),
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
    run.state = (
        "BLOCKED" if outcome == "BLOCKED" else "FAILED" if outcome == "FAILED" else "COMPLETED"
    )
    run.block_reasons = list(block_reasons or [])
    run.completed_at = completed_at
    run.lease_owner = None
    run.lease_token = None
    run.lease_expires_at = None
    parent = (
        database.get(CoordinatedMarketResearchRun, run.coordinated_run_id)
        if run.coordinated_run_id
        else None
    )
    if parent is not None:
        if outcome in {"BLOCKED", "FAILED"}:
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
            notify_market_research_owners(
                database,
                kind="CATEGORY_BLOCKED",
                subject_id=str(run.id),
                payload={
                    "category": run.category,
                    "outcome": outcome,
                    "block_reasons": list(block_reasons or []),
                    "active_assignment_changed": False,
                },
                created_at=completed_at,
            )
        children = list(
            database.scalars(
                select(MarketResearchRun).where(MarketResearchRun.coordinated_run_id == parent.id)
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
            if parent.occurrence_id is not None:
                occurrence = database.get(MarketResearchOccurrence, parent.occurrence_id)
                if occurrence is not None:
                    occurrence.state = parent.state
                    occurrence.lease_owner = None
                    occurrence.lease_token = None
                    occurrence.lease_expires_at = None
            emit_market_research_fact(
                database,
                aggregate_type="coordinated_market_research_run",
                aggregate_id=parent.id,
                aggregate_version=parent.version,
                event_type=COORDINATED_COMPLETED,
                data={
                    "state": parent.state,
                    "category_outcomes": {child.category: child.state for child in children},
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
        candidate_rows = [
            {
                "id": str(assessment.id),
                "instrument_id": str(instrument.id),
                "symbol": instrument.symbol,
                "display_name": instrument.display_name,
                "eligible": assessment.eligible,
                "score": str(assessment.score) if assessment.score is not None else None,
                "rank": assessment.rank,
                "confidence": str(assessment.confidence),
                "exclusions": assessment.gate_evidence.get("reason_codes", []),
                "components": assessment.components,
                "rationale": assessment.explanation,
                "source_evidence": assessment.source_evidence,
            }
            for assessment, instrument in assessment_rows
        ]
        eligible_candidates = [
            item for item in candidate_rows if child.state == "COMPLETED" and item["eligible"]
        ]
        proposed_candidate = min(
            eligible_candidates,
            key=lambda item: (item["rank"] is None, item["rank"] or 999999, item["symbol"]),
            default=None,
        )
        latest_attempt = database.scalar(
            select(LlmAnalysisAttempt)
            .where(LlmAnalysisAttempt.research_run_id == child.id)
            .order_by(LlmAnalysisAttempt.attempt_number.desc())
            .limit(1)
        )
        llm_analysis: dict[str, object] = {
            "state": child.llm_analysis_state,
            "authoritative": False,
            "provider": parent.llm_provider_key,
            "exact_model_id": parent.exact_model_id,
            "catalogue_revision": parent.llm_catalogue_revision,
            "adapter_revision": parent.llm_adapter_revision,
            "prompt_template_version": parent.prompt_template_version,
            "output_schema_version": parent.output_schema_version,
            "inference_policy_version": parent.inference_policy_version,
            "research_brief": parent.research_brief,
            "attempt_count": latest_attempt.attempt_number if latest_attempt else 0,
            "retry_eligible": child.llm_analysis_state not in {"COMPLETED", "RUNNING"},
            "analysis": latest_attempt.analysis if latest_attempt else None,
            "failure_reason": (
                latest_attempt.failure_reason or latest_attempt.state
                if latest_attempt and latest_attempt.state != "COMPLETED"
                else child.current_error
            ),
        }
        outcome = (
            "BLOCKED"
            if child.state in {"BLOCKED", "FAILED"}
            else "RECOMMENDED"
            if child.state == "COMPLETED" and proposed_candidate is not None
            else "NO_ELIGIBLE_CANDIDATE"
            if child.state == "COMPLETED"
            else "PENDING"
        )
        categories.append(
            {
                "run_id": str(child.id),
                "category": child.category,
                "state": child.state,
                "outcome": outcome,
                "block_reasons": child.block_reasons,
                "source_manifest": child.source_manifest,
                "fallback_path": child.fallback_path,
                "deterministic_result_hash": child.deterministic_result_hash,
                "policy_pins": child.policy_pins,
                "llm_analysis": llm_analysis,
                "activation_state": "REQUIRES_SEPARATE_HUMAN_CONFIRMATION",
                "candidates": candidate_rows,
                "selection_proposal": (
                    {
                        "state": "REVIEW_REQUIRED",
                        "candidate": proposed_candidate,
                        "active_assignment_changed": False,
                    }
                    if proposed_candidate is not None
                    else None
                ),
            }
        )
    return {
        "id": str(parent.id),
        "state": parent.state,
        "trigger": parent.trigger,
        "created_at": parent.created_at.isoformat(),
        "completed_at": parent.completed_at.isoformat() if parent.completed_at else None,
        "methodology_version": parent.methodology_version,
        "source_catalogue_revision": parent.source_catalogue_revision,
        "exact_model_id": parent.exact_model_id,
        "research_brief": parent.research_brief,
        "freshness_policy_manifest": parent.freshness_policy_manifest,
        "retry_policy_manifest": parent.retry_policy_manifest,
        "model_pin": {
            "provider": parent.llm_provider_key,
            "exact_model_id": parent.exact_model_id,
            "catalogue_revision": parent.llm_catalogue_revision,
            "adapter_revision": parent.llm_adapter_revision,
            "prompt_template_version": parent.prompt_template_version,
            "output_schema_version": parent.output_schema_version,
            "inference_policy_version": parent.inference_policy_version,
            "research_brief": parent.research_brief,
        },
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
