"""Add fenced category-run leases and durable failure diagnostics.

Revision ID: 0025_research_leases
Revises: 0024_nullable_metrics
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_research_leases"
down_revision = "0024_nullable_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("market_research_runs")
    }
    columns = (
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_token", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_error", sa.String(2000), nullable=True),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("market_research_runs", column)


def downgrade() -> None:
    raise RuntimeError("market-research recovery evidence must be retained")
