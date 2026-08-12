from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin


class OpportunityState(StrEnum):
    NO_TRADE = "NO_TRADE"
    CANDIDATE = "CANDIDATE"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"


class Opportunity(IdentifiedMixin, Base):
    __tablename__ = "opportunities"
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    score: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityScoreComponent(IdentifiedMixin, Base):
    __tablename__ = "opportunity_score_components"
    opportunity_id: Mapped[UUID] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
