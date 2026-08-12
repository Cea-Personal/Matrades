from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin
from traderx.shared.types import DataQuality, RiskDecisionKind, RiskState


class AccountSnapshot(IdentifiedMixin, Base):
    __tablename__ = "account_snapshots"

    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(256), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    balance: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    equity: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    realized_pl: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    floating_pl: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    quality: Mapped[str] = mapped_column(String(16), default=DataQuality.UNKNOWN, nullable=False)


class RiskSnapshot(IdentifiedMixin, Base):
    __tablename__ = "risk_snapshots"

    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    account_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("account_snapshots.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(16), default=RiskState.LOCKDOWN, nullable=False)
    capacity: Mapped[int] = mapped_column(nullable=False, default=0)
    quality: Mapped[str] = mapped_column(String(16), default=DataQuality.UNKNOWN, nullable=False)
    remaining_daily_margin: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    remaining_drawdown_margin: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    open_risk: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RiskDecision(IdentifiedMixin, Base):
    __tablename__ = "risk_decisions"

    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    risk_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("risk_snapshots.id"), nullable=False)
    opportunity_id: Mapped[UUID | None] = mapped_column(nullable=True)
    decision: Mapped[str] = mapped_column(
        String(16), default=RiskDecisionKind.BLOCKED, nullable=False
    )
    requested_risk: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    permitted_risk: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CircuitBreakerState(StrEnum):
    ARMED = "ARMED"
    TRIPPED = "TRIPPED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLEARED = "CLEARED"


class CircuitBreaker(IdentifiedMixin, Base):
    __tablename__ = "circuit_breakers"

    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trading_accounts.id"), nullable=True
    )
    breaker_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), default=CircuitBreakerState.ARMED, nullable=False
    )
    trigger_evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    tripped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[UUID | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
