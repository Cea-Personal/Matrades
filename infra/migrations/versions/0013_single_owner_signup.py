"""Reserve one database-backed owner signup slot per installation."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The API may have already created this table through metadata.create_all.
    if "auth_signup_gate" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "auth_signup_gate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, unique=True),
    )


def downgrade() -> None:
    op.drop_table("auth_signup_gate")
