from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class TradeThesis(IdentifiedMixin, Base):
    __tablename__ = "trade_theses"
    position_id: Mapped[UUID] = mapped_column(
        ForeignKey("positions.id"), unique=True, nullable=False
    )
    recommendation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recommendations.id"), nullable=True
    )
    frozen_evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MonitoringObservation(IdentifiedMixin, Base):
    __tablename__ = "monitoring_observations"
    thesis_id: Mapped[UUID] = mapped_column(ForeignKey("trade_theses.id"), nullable=False)
    health: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
