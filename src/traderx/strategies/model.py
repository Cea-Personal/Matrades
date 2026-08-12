from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class StrategyLifecycle(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    QUALIFIED = "QUALIFIED"
    PAPER = "PAPER"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


class Strategy(IdentifiedMixin, Base):
    __tablename__ = "strategies"
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    instrument_id: Mapped[UUID | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategyVersion(IdentifiedMixin, Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),)

    strategy_id: Mapped[UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    definition: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    lifecycle: Mapped[str] = mapped_column(
        String(32), default=StrategyLifecycle.DRAFT, nullable=False
    )
    parent_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
