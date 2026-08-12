"""Create market-data and market-research evidence tables.

Revision ID: 0003_markets
Revises: 0002_identity_accounts_risk
"""

from alembic import op

revision = "0003_markets"
down_revision = "0002_identity_accounts_risk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.market_data import model as market_data_model  # noqa: F401
    from traderx.market_research import model as market_research_model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("market knowledge is retained; use an explicit governed retention migration")
