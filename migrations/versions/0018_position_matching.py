"""Persist position classification evidence.

Revision ID: 0018_position_matching
Revises: 0017_paper_workflows
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_position_matching"
down_revision = "0017_paper_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("positions")}
    if "matched_recommendation_id" not in columns:
        op.add_column("positions", sa.Column("matched_recommendation_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_positions_matched_recommendation_id_recommendations",
            "positions",
            "recommendations",
            ["matched_recommendation_id"],
            ["id"],
        )
    if "match_confidence" not in columns:
        op.add_column(
            "positions",
            sa.Column("match_confidence", sa.Numeric(38, 18), nullable=False, server_default="0"),
        )
    if "classification_reason" not in columns:
        op.add_column(
            "positions",
            sa.Column(
                "classification_reason", sa.String(128), nullable=False, server_default="UNRESOLVED"
            ),
        )


def downgrade() -> None:
    raise RuntimeError("position classification evidence must be retained")
