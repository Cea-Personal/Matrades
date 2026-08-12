from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin


class JournalEntry(IdentifiedMixin, Base):
    __tablename__ = "journal_entries"
    position_id: Mapped[UUID | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    paper_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("paper_runs.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_id: Mapped[UUID | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    gross_pnl: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    net_pnl: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    r_multiple: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    correction_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True
    )
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JournalAnnotation(IdentifiedMixin, Base):
    __tablename__ = "journal_annotations"
    entry_id: Mapped[UUID] = mapped_column(ForeignKey("journal_entries.id"), nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("journal_annotations.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(String(10000), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JournalAttachment(IdentifiedMixin, Base):
    __tablename__ = "journal_attachments"
    entry_id: Mapped[UUID] = mapped_column(ForeignKey("journal_entries.id"), nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchProposal(IdentifiedMixin, Base):
    __tablename__ = "research_proposals"
    strategy_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=True
    )
    evidence_links: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    hypothesis: Mapped[str] = mapped_column(String(10000), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="PROPOSED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
