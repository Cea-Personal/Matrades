"""Create paper-trading and approval evidence tables.

Revision ID: 0005_paper_approval
Revises: 0004_strategy_validation
"""

from alembic import op

revision = "0005_paper_approval"
down_revision = "0004_strategy_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.paper import model as paper_model  # noqa: F401
    from traderx.shared.db import Base
    from traderx.strategies import approval_model  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("paper and approval evidence must be retained")
