"""Create opportunity and recommendation tables.

Revision ID: 0006_opportunities
Revises: 0005_paper_approval
"""

from alembic import op

revision = "0006_opportunities"
down_revision = "0005_paper_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.opportunities import model as opportunities_model  # noqa: F401
    from traderx.opportunities import recommendation_model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("recommendation evidence must be retained")
