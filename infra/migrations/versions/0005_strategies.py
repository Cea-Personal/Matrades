"""Origin-neutral strategies, validation, paper, and promotion evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    for name in (
        "strategy_drafts",
        "strategy_suggestions",
        "strategies",
        "strategy_versions",
        "strategy_fingerprints",
        "strategy_lineage",
        "validation_evidence",
        "paper_runs",
        "promotions",
    ):
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("payload", sa.JSON(), nullable=False),
        )


def downgrade():
    for name in reversed(
        (
            "strategy_drafts",
            "strategy_suggestions",
            "strategies",
            "strategy_versions",
            "strategy_fingerprints",
            "strategy_lineage",
            "validation_evidence",
            "paper_runs",
            "promotions",
        )
    ):
        op.drop_table(name)
