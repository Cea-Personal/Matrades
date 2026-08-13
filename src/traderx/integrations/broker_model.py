from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class BrokerProvider(StrEnum):
    OANDA_V20 = "OANDA_V20"
    MT5_TERMINAL_BRIDGE = "MT5_TERMINAL_BRIDGE"


class BrokerIntegrationProfile(IdentifiedMixin, Base):
    """Non-secret configuration for a single read-only broker connection."""

    __tablename__ = "broker_integration_profiles"
    __table_args__ = (UniqueConstraint("integration_id", name="uq_broker_integration_profile"),)

    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bridge_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    bridge_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    account_login: Mapped[str | None] = mapped_column(String(256), nullable=True)
    server: Mapped[str | None] = mapped_column(String(256), nullable=True)
    selected_provider_account_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class BrokerDiscoveredAccount(IdentifiedMixin, Base):
    __tablename__ = "broker_discovered_accounts"
    __table_args__ = (
        UniqueConstraint(
            "integration_id", "provider_account_id", name="uq_broker_discovered_account"
        ),
    )

    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    provider_account_id: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    account_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="DISCOVERED"
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BrokerReconciliationCheckpoint(IdentifiedMixin, Base):
    """Append-only provider checkpoint; the cursor is never returned by the API."""

    __tablename__ = "broker_reconciliation_checkpoints"

    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("trading_accounts.id"), nullable=False)
    account_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("account_snapshots.id"), nullable=True
    )
    source_cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_window: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    validation_outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(128), nullable=False)
