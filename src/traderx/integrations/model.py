from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
    provider_catalogue_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("provider_catalogue_entries.id"), nullable=True
    )
    catalogue_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adapter_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entitlement_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="UNVERIFIED"
    )
    retention_posture: Mapped[str] = mapped_column(
        String(24), nullable=False, default="NOT_APPLICABLE"
    )
    licensing_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderCatalogueEntry(IdentifiedMixin, Base):
    __tablename__ = "provider_catalogue_entries"
    __table_args__ = (
        UniqueConstraint("provider_key", "catalogue_revision", name="uq_provider_catalogue_rev"),
    )

    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    catalogue_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False, default="APPROVED")
    asset_categories: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    venues: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    capability_semantics: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    configuration_schema: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    credential_schema: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    permitted_models: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    licensing_notice: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    retention_posture: Mapped[str] = mapped_column(
        String(24), nullable=False, default="NOT_APPLICABLE"
    )
    official_source_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    enabled_by_default: Mapped[bool] = mapped_column(nullable=False, default=False)


class FreshnessPolicyVersion(IdentifiedMixin, Base):
    __tablename__ = "freshness_policy_versions"
    __table_args__ = (
        UniqueConstraint(
            "provider_key", "capability", "policy_version", name="uq_freshness_policy_rev"
        ),
    )

    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    maximum_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default="MARKET_SELECTION")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetryPolicyVersion(IdentifiedMixin, Base):
    __tablename__ = "retry_policy_versions"
    __table_args__ = (
        UniqueConstraint("provider_key", "policy_version", name="uq_retry_policy_rev"),
    )

    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    maximum_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    attempt_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    overall_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    backoff_seconds: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    honors_retry_after: Mapped[bool] = mapped_column(nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    affected_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
