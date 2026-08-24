"""Owner-scoped knowledge provenance and vector index."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("knowledge_sources.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
    )
    op.create_table(
        "knowledge_segments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id", sa.Uuid(), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.String(), nullable=True),
    )
    op.create_table(
        "retrieval_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    for name in (
        "retrieval_audits",
        "knowledge_segments",
        "knowledge_documents",
        "knowledge_sources",
    ):
        op.drop_table(name)
