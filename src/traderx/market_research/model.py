from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin


class ResearchRunState(StrEnum):
    QUEUED = "QUEUED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MarketResearchRun(IdentifiedMixin, Base):
    __tablename__ = "market_research_runs"

    category: Mapped[str] = mapped_column(String(24), nullable=False)
    method_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=ResearchRunState.QUEUED, nullable=False)
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
