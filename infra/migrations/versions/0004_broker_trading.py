"""Read-only broker reconciliation and management recommendations."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    for name in (
        "broker_positions",
        "broker_events",
        "reconciliations",
        "active_trades",
        "management_recommendations",
    ):
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade():
    for name in reversed(
        (
            "broker_positions",
            "broker_events",
            "reconciliations",
            "active_trades",
            "management_recommendations",
        )
    ):
        op.drop_table(name)
