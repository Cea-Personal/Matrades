from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin


class AccountMode(StrEnum):
    LIVE = "LIVE"
    PAPER = "PAPER"
    DEMO = "DEMO"


class AccountStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"


class TradingAccount(IdentifiedMixin, Base):
    __tablename__ = "trading_accounts"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default=AccountMode.LIVE, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    broker_integration_id: Mapped[UUID | None] = mapped_column(nullable=True)
    provider_account_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    starting_balance: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    prop_profile_id: Mapped[UUID | None] = mapped_column(nullable=True)
    risk_policy_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=AccountStatus.DRAFT, nullable=False)


class PropProfileVersion(IdentifiedMixin, Base):
    __tablename__ = "prop_profile_versions"

    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    profile_version: Mapped[int] = mapped_column(nullable=False)
    daily_loss_limit: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    maximum_loss_limit: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    trailing_drawdown: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    floating_loss_counts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reset_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    reset_time: Mapped[str] = mapped_column(String(8), nullable=False)
    restrictions: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)


class RiskPolicyVersion(IdentifiedMixin, Base):
    __tablename__ = "risk_policy_versions"

    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    policy_version: Mapped[int] = mapped_column(nullable=False)
    maximum_risk_per_trade: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    maximum_portfolio_risk: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    internal_daily_loss_limit: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    internal_drawdown_limit: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    minimum_prop_buffer: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    maximum_positions: Mapped[int] = mapped_column(nullable=False, default=2)
    correlation_limit: Mapped[object] = mapped_column(FinancialDecimal, nullable=False)
    state_thresholds: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
