"""Typed instrument matrix storage with legacy records preserved as JSON."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These tables deliberately keep provider-specific terms in JSON.  The
    # domain models validate the shape while the migration remains portable
    # across PostgreSQL and the SQLite test database.
    op.create_table(
        "typed_underlyings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "typed_venue_instruments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("underlying_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("instrument_type", sa.String(16), nullable=False),
        sa.Column("venue", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("executable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_typed_venue_lane_symbol",
        "typed_venue_instruments",
        ["owner_id", "asset_class", "instrument_type", "symbol"],
        unique=False,
    )
    op.create_table(
        "typed_specifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("venue_instrument_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "venue_instrument_id", "version", name="uq_typed_specification_version"
        ),
    )
    op.create_table(
        "research_matrix_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("account_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("lanes", sa.JSON(), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "version", name="uq_research_matrix_account_version"),
    )
    op.create_table(
        "research_provider_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("account_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("lane", sa.JSON(), nullable=False),
        sa.Column("capability", sa.String(48), nullable=False),
        sa.Column("authority_purpose", sa.String(48), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("verification_status", sa.String(16), nullable=False),
        sa.Column("freshness_policy", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "research_provider_bindings",
        "research_matrix_versions",
        "typed_specifications",
        "typed_venue_instruments",
        "typed_underlyings",
    ):
        op.drop_table(table)
