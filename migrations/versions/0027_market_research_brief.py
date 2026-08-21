"""Persist versioned advisory research briefs and pin them to coordinated runs.

Revision ID: 0027_market_research_brief
Revises: 0026_market_data_calendar_risk
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_market_research_brief"
down_revision = "0026_market_data_calendar_risk"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column[object]) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing(
        "market_research_model_configurations",
        sa.Column("research_brief", sa.String(4000), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "coordinated_market_research_runs",
        sa.Column("research_brief", sa.String(4000), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError("research briefs are retained with their audit and run history")
