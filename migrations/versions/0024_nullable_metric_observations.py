"""Allow metric-only market observations to preserve absent OHLC values.

Revision ID: 0024_nullable_metrics
Revises: 0023_market_research_automation
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_nullable_metrics"
down_revision = "0023_market_research_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("market_observations") as batch:
        for column in ("open", "high", "low", "close"):
            batch.alter_column(
                column,
                existing_type=sa.Numeric(38, 18),
                nullable=True,
            )


def downgrade() -> None:
    raise RuntimeError("provider-native metric evidence must be retained")
