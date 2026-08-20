"""Persist aggregate market-data provenance and official calendar risk evidence.

Revision ID: 0026_market_data_calendar_risk
Revises: 0025_research_leases
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_market_data_calendar_risk"
down_revision = "0025_research_leases"
branch_labels = None
depends_on = None


def _add_columns(table: str, columns: tuple[sa.Column[object], ...]) -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    _add_columns(
        "economic_events",
        (
            sa.Column("source_provider", sa.String(128), nullable=False, server_default="OWNER"),
            sa.Column("external_id", sa.String(256), nullable=False, server_default=""),
            sa.Column("source_origin", sa.String(32), nullable=False, server_default="OWNER_CITED"),
            sa.Column("source_url", sa.String(2048), nullable=False, server_default=""),
            sa.Column("canonical_type", sa.String(128), nullable=False, server_default="OTHER"),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("affected_categories", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("affected_instruments", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(32), nullable=False, server_default="UPCOMING"),
            sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("stale_after", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by", sa.Uuid(), nullable=True),
            sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        ),
    )
    op.create_unique_constraint("uq_economic_event_source", "economic_events", ["source_provider", "external_id"])
    op.create_table(
        "calendar_coverages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_provider", sa.String(128), nullable=False),
        sa.Column("scope_key", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("covered_through", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("source_provider", "scope_key", name="uq_calendar_coverage_scope"),
    )
    op.create_table(
        "economic_event_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("economic_event_id", sa.Uuid(), sa.ForeignKey("economic_events.id"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("changed_by", sa.Uuid()),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "event_risk_policy_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("trading_accounts.id"), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("enabled_event_types", sa.JSON(), nullable=False),
        sa.Column("pre_buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("post_buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("coverage_required", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("configured_by", sa.Uuid()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("economic-calendar and event-risk evidence is append-only")
