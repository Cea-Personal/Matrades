from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class EvidenceState(StrEnum):
    PENDING = "PENDING"
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BacktestRun(IdentifiedMixin, Base):
    __tablename__ = "backtest_runs"
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=EvidenceState.PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ValidationRun(IdentifiedMixin, Base):
    __tablename__ = "validation_runs"
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )
    backtest_run_id: Mapped[UUID] = mapped_column(ForeignKey("backtest_runs.id"), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    seed: Mapped[int] = mapped_column(nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=EvidenceState.PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
