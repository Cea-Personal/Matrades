from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin


class RecommendationState(StrEnum):
    ISSUED = "ISSUED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"


class Recommendation(IdentifiedMixin, Base):
    __tablename__ = "recommendations"
    opportunity_id: Mapped[UUID] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    risk_decision_id: Mapped[UUID] = mapped_column(ForeignKey("risk_decisions.id"), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), default=RecommendationState.ISSUED, nullable=False
    )
    entry: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    stop: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    volume: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    targets: Mapped[list[object]] = mapped_column(JSON, default=list, nullable=False)
    invalidation: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    reason_trace: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
