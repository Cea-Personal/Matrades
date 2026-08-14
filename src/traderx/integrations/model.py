from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class Integration(IdentifiedMixin, Base):
    __tablename__ = "integrations"
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False, default="BROKER_ACCOUNT_DATA")
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="DISABLED")
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    official_source: Mapped[bool] = mapped_column(nullable=False, default=True)


class CredentialVersion(IdentifiedMixin, Base):
    __tablename__ = "credential_versions"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    key_version: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(String(4096), nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntegrationHealthObservation(IdentifiedMixin, Base):
    __tablename__ = "integration_health_observations"
    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
