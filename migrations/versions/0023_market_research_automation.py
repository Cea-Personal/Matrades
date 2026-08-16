"""Add reviewed providers and coordinated market-research automation.

Revision ID: 0023_market_research_automation
Revises: 0022_authentication_throttles
"""

from collections.abc import Iterable

import sqlalchemy as sa
from alembic import op

revision = "0023_market_research_automation"
down_revision = "0022_authentication_throttles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.integrations import model as integration_model  # noqa: F401
    from traderx.market_data import model as market_data_model  # noqa: F401
    from traderx.market_research import model as market_research_model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)

    _add_columns(
        "integrations",
        (
            sa.Column("provider_catalogue_id", sa.Uuid(), nullable=True),
            sa.Column("catalogue_revision", sa.String(64), nullable=True),
            sa.Column("adapter_revision", sa.String(64), nullable=True),
            sa.Column(
                "entitlement_status",
                sa.String(24),
                nullable=False,
                server_default="UNVERIFIED",
            ),
            sa.Column(
                "retention_posture",
                sa.String(24),
                nullable=False,
                server_default="NOT_APPLICABLE",
            ),
            sa.Column("licensing_accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        ),
    )
    _add_columns(
        "integration_health_observations",
        (
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("current_error", sa.String(2000), nullable=True),
            sa.Column("affected_capabilities", sa.JSON(), nullable=False, server_default="[]"),
        ),
    )
    _add_columns(
        "instrument_aliases",
        (
            sa.Column("integration_id", sa.Uuid(), nullable=True),
            sa.Column("venue", sa.String(128), nullable=True),
            sa.Column("mapping_revision", sa.String(64), nullable=False, server_default="v1"),
            sa.Column("contract_variant", sa.String(128), nullable=True),
            sa.Column("provider_metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("approved_by", sa.Uuid(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        ),
    )
    _add_columns(
        "dataset_manifests",
        (
            sa.Column("integration_id", sa.Uuid(), nullable=True),
            sa.Column("provider_symbol", sa.String(256), nullable=True),
            sa.Column("venue", sa.String(128), nullable=True),
            sa.Column("capability", sa.String(64), nullable=False, server_default="CANDLES"),
            sa.Column("semantics", sa.String(24), nullable=False, server_default="UNAVAILABLE"),
            sa.Column(
                "source_role", sa.String(32), nullable=False, server_default="SPECIALIST_PRIMARY"
            ),
            sa.Column("catalogue_revision", sa.String(64), nullable=True),
            sa.Column("adapter_revision", sa.String(64), nullable=True),
            sa.Column("mapping_revision", sa.String(64), nullable=True),
            sa.Column("freshness_policy_version", sa.String(64), nullable=True),
            sa.Column("retry_policy_version", sa.String(64), nullable=True),
            sa.Column(
                "entitlement_status",
                sa.String(24),
                nullable=False,
                server_default="UNVERIFIED",
            ),
            sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("quality", sa.String(24), nullable=False, server_default="UNKNOWN"),
            sa.Column("conflict_state", sa.String(24), nullable=False, server_default="UNCHECKED"),
            sa.Column("fallback_reason", sa.String(2000), nullable=True),
            sa.Column("raw_reference", sa.String(1024), nullable=True),
        ),
    )
    _add_columns(
        "market_observations",
        (
            sa.Column("integration_id", sa.Uuid(), nullable=True),
            sa.Column("dataset_manifest_id", sa.Uuid(), nullable=True),
            sa.Column("provider", sa.String(120), nullable=False, server_default="UNKNOWN"),
            sa.Column("provider_symbol", sa.String(256), nullable=True),
            sa.Column("venue", sa.String(128), nullable=True),
            sa.Column("capability", sa.String(64), nullable=False, server_default="CANDLES"),
            sa.Column("semantics", sa.String(24), nullable=False, server_default="UNAVAILABLE"),
            sa.Column(
                "source_role", sa.String(32), nullable=False, server_default="SPECIALIST_PRIMARY"
            ),
            sa.Column("mapping_revision", sa.String(64), nullable=True),
            sa.Column("freshness_policy_version", sa.String(64), nullable=True),
            sa.Column("measures", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("conflict_state", sa.String(24), nullable=False, server_default="CLEAR"),
            sa.Column("raw_reference", sa.String(1024), nullable=True),
        ),
    )
    _add_columns(
        "market_research_runs",
        (
            sa.Column("coordinated_run_id", sa.Uuid(), nullable=True),
            sa.Column("source_manifest", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("fallback_path", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("block_reasons", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("deterministic_result_hash", sa.String(64), nullable=True),
            sa.Column("policy_pins", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column(
                "llm_analysis_state",
                sa.String(24),
                nullable=False,
                server_default="NOT_REQUESTED",
            ),
        ),
    )
    _add_columns(
        "candidate_assessments",
        (
            sa.Column("source_evidence", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("deterministic_result_hash", sa.String(64), nullable=True),
        ),
    )


def _add_columns(table_name: str, columns: Iterable[sa.Column[object]]) -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def downgrade() -> None:
    raise RuntimeError("market research, provider, schedule, and LLM evidence must be retained")
