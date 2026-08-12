from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin


class PositionClassification(StrEnum):
    RECOMMENDED = "RECOMMENDED"
    DISCRETIONARY = "DISCRETIONARY"
    UNRESOLVED = "UNRESOLVED"


class Position(IdentifiedMixin, Base):
    __tablename__ = "positions"
    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    provider_position_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    volume: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    open_risk: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    classification: Mapped[str] = mapped_column(
        String(24), default=PositionClassification.UNRESOLVED, nullable=False
    )
    provider_revision: Mapped[int] = mapped_column(nullable=False, default=1)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TradeExecution(IdentifiedMixin, Base):
    __tablename__ = "trade_executions"
    __table_args__ = (UniqueConstraint("provider_deal_id", name="uq_provider_deal"),)
    position_id: Mapped[UUID] = mapped_column(ForeignKey("positions.id"), nullable=False)
    provider_deal_id: Mapped[str] = mapped_column(String(256), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    volume: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
