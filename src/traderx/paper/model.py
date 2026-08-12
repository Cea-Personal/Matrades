from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin


class PaperRunState(StrEnum):
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class PaperRun(IdentifiedMixin, Base):
    __tablename__ = "paper_runs"
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), default=PaperRunState.RUNNING, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PaperComparison(IdentifiedMixin, Base):
    __tablename__ = "paper_comparisons"
    paper_run_id: Mapped[UUID] = mapped_column(ForeignKey("paper_runs.id"), nullable=False)
    historical_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    divergence: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    criteria: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)


class PaperTradeReference(IdentifiedMixin, Base):
    __tablename__ = "paper_trade_references"
    paper_run_id: Mapped[UUID] = mapped_column(ForeignKey("paper_runs.id"), nullable=False)
    entry: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    exit: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    units: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
