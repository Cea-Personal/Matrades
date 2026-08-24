"""Journal, performance, strategy health and notification projections."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    for name in (
        "journal_projections",
        "performance_records",
        "strategy_health",
        "research_triggers",
        "notifications",
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
            "journal_projections",
            "performance_records",
            "strategy_health",
            "research_triggers",
            "notifications",
        )
    ):
        op.drop_table(name)
