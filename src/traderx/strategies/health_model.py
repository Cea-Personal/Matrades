from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class StrategyHealthObservation(IdentifiedMixin, Base):
    __tablename__ = "strategy_health_observations"
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategySuspension(IdentifiedMixin, Base):
    __tablename__ = "strategy_suspensions"
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
