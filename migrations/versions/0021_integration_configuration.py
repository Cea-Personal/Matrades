"""Add governed non-broker integration configuration.

Revision ID: 0021_integration_configuration
Revises: 0020_journal_attachment_content
"""

import sqlalchemy as sa
from alembic import op

revision = "0021_integration_configuration"
down_revision = "0020_journal_attachment_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("integrations")}
    if "category" not in columns:
        op.add_column(
            "integrations",
            sa.Column(
                "category", sa.String(48), nullable=False, server_default="BROKER_ACCOUNT_DATA"
            ),
        )
    if "configuration" not in columns:
        op.add_column(
            "integrations",
            sa.Column("configuration", sa.JSON(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    raise RuntimeError("integration configuration evidence must be retained")
