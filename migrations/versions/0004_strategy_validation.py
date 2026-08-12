"""Create immutable strategy and validation evidence tables.

Revision ID: 0004_strategy_validation
Revises: 0003_markets
"""

from alembic import op

revision = "0004_strategy_validation"
down_revision = "0003_markets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.research import model as research_model  # noqa: F401
    from traderx.shared.db import Base
    from traderx.strategies import model as strategies_model  # noqa: F401
    from traderx.validation import model as validation_model  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("strategy and validation evidence must be retained")
