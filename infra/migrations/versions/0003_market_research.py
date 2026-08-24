"""Market observations and research selections."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instruments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("symbol", sa.String(40), nullable=False, unique=True),
        sa.Column("category", sa.String(20), nullable=False),
    )
    op.create_table(
        "market_observations",
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("instrument_id", "observed_at", "source"),
    )
    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "market_selections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("research_runs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.execute(
        "SELECT create_hypertable('market_observations', 'observed_at', if_not_exists => TRUE)"
    )


def downgrade():
    for name in ("market_selections", "research_runs", "market_observations", "instruments"):
        op.drop_table(name)
