from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin


class ResearchRunState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MarketResearchModelConfiguration(IdentifiedMixin, Base):
    __tablename__ = "market_research_model_configurations"
    __table_args__ = (UniqueConstraint("scope", name="uq_market_research_model_scope"),)

    scope: Mapped[str] = mapped_column(String(24), nullable=False, default="GLOBAL")
    llm_integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    exact_model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    catalogue_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    inference_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by: Mapped[UUID] = mapped_column(nullable=False)
    change_reason: Mapped[str] = mapped_column(String(2000), nullable=False)


class MarketResearchSchedule(IdentifiedMixin, Base):
    __tablename__ = "market_research_schedules"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_market_research_schedule_account"),
        CheckConstraint(
            "interval_seconds >= 3600 AND interval_seconds <= 2592000",
            name="market_research_schedule_interval",
        ),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    anchored_start_local: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    account_timezone: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone_policy_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="iana-v1"
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    changed_by: Mapped[UUID] = mapped_column(nullable=False)
    change_reason: Mapped[str] = mapped_column(String(2000), nullable=False)


class MarketResearchOccurrence(IdentifiedMixin, Base):
    __tablename__ = "market_research_occurrences"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_research_occurrence_due"),
    )

    schedule_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_research_schedules.id"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="CLAIMED")
    coordinated_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("coordinated_market_research_runs.id", use_alter=True), nullable=True
    )
    active_run_id: Mapped[UUID | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CoordinatedMarketResearchRun(IdentifiedMixin, Base):
    __tablename__ = "coordinated_market_research_runs"
    __table_args__ = (
        CheckConstraint("expected_category_count = 3", name="coordinated_run_three_categories"),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    occurrence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("market_research_occurrences.id", use_alter=True), nullable=True, unique=True
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    expected_category_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_catalogue_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    freshness_policy_manifest: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    retry_policy_manifest: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    llm_integration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("integrations.id"), nullable=True
    )
    llm_provider_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exact_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    llm_catalogue_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_adapter_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_template_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inference_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_summary: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class MarketResearchRun(IdentifiedMixin, Base):
    __tablename__ = "market_research_runs"
    __table_args__ = (
        UniqueConstraint("coordinated_run_id", "category", name="uq_coordinated_category_run"),
    )

    coordinated_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("coordinated_market_research_runs.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    method_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=ResearchRunState.QUEUED, nullable=False)
    source_manifest: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    fallback_path: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    block_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    deterministic_result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_pins: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    llm_analysis_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="NOT_REQUESTED"
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CandidateAssessment(IdentifiedMixin, Base):
    __tablename__ = "candidate_assessments"
    __table_args__ = (
        UniqueConstraint("research_run_id", "instrument_id", name="uq_assessment_run"),
    )

    research_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_research_runs.id"), nullable=False
    )
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    eligible: Mapped[bool] = mapped_column(nullable=False)
    gate_evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    components: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    score: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    rank: Mapped[int | None] = mapped_column(nullable=True)
    confidence: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    explanation: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    source_evidence: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    deterministic_result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LlmAnalysisAttempt(IdentifiedMixin, Base):
    __tablename__ = "llm_analysis_attempts"
    __table_args__ = (
        UniqueConstraint("research_run_id", "attempt_number", name="uq_llm_attempt_number"),
    )

    research_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_research_runs.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    exact_model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    catalogue_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    inference_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    usage: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    analysis: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    explicit_retry: Mapped[bool] = mapped_column(nullable=False, default=False)


class AssignmentState(StrEnum):
    ACTIVE = "ACTIVE"
    REPLACED = "REPLACED"
    DEACTIVATED = "DEACTIVATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


class ActiveMarketAssignment(IdentifiedMixin, Base):
    __tablename__ = "active_market_assignments"
    __table_args__ = (
        UniqueConstraint("category", "effective_from", name="uq_assignment_effective"),
    )

    category: Mapped[str] = mapped_column(String(24), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    candidate_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_assessments.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(24), default=AssignmentState.AWAITING_APPROVAL, nullable=False
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(nullable=True)
    approval_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
