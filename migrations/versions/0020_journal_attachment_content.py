"""Store protected journal attachment content behind authenticated routes.

Revision ID: 0020_journal_attachment_content
Revises: 0019_notification_read_state
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_journal_attachment_content"
down_revision = "0019_notification_read_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("journal_attachments")
    }
    additions = (
        ("original_name", sa.String(512)),
        ("media_type", sa.String(128)),
        ("content", sa.LargeBinary()),
        ("uploaded_by", sa.Uuid()),
    )
    for name, type_ in additions:
        if name not in columns:
            op.add_column("journal_attachments", sa.Column(name, type_, nullable=True))
    foreign_keys = {
        key.get("name") for key in sa.inspect(op.get_bind()).get_foreign_keys("journal_attachments")
    }
    if "fk_journal_attachments_uploaded_by_users" not in foreign_keys:
        op.create_foreign_key(
            "fk_journal_attachments_uploaded_by_users",
            "journal_attachments",
            "users",
            ["uploaded_by"],
            ["id"],
        )


def downgrade() -> None:
    raise RuntimeError("protected journal attachment evidence must be retained")
