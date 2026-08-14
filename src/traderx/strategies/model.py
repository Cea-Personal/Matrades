from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class StrategyLifecycle(StrEnum):
    DRAFT = "DRAFT"
    RESEARCH = "RESEARCH"
    BACKTESTING = "BACKTESTING"
    VALIDATING = "VALIDATING"
    BACKTEST_PASSED = "BACKTEST_PASSED"
    QUALIFIED = "BACKTEST_PASSED"
    PAPER_READY = "PAPER_READY"
    PAPER_TRADING = "PAPER_TRADING"
    PAPER = "PAPER_TRADING"
    PAPER_PASSED = "PAPER_PASSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    LIVE_APPROVED = "LIVE_APPROVED"
    LIVE_ELIGIBLE = "LIVE_APPROVED"
    LIVE = "LIVE"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    WATCH = "WATCH"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"
    STALE = "STALE"


class Strategy(IdentifiedMixin, Base):
    __tablename__ = "strategies"
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    instrument_id: Mapped[UUID | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    owner_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategyVersion(IdentifiedMixin, Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "sequence", name="uq_strategy_version"),)

    strategy_id: Mapped[UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    lifecycle: Mapped[str] = mapped_column(
        String(32), default=StrategyLifecycle.DRAFT, nullable=False
    )
    parent_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=True
    )
    change_summary: Mapped[str] = mapped_column(
        String(2000), nullable=False, default="Initial draft"
    )
    author_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
