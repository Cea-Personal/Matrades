"""Add broker-account truth, discovery, and reconciliation evidence.

Revision ID: 0013_broker_account_truth
Revises: 0012_identity_recovery
"""

from alembic import op

revision = "0013_broker_account_truth"
down_revision = "0012_identity_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.integrations import broker_model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[
            Base.metadata.tables["broker_integration_profiles"],
            Base.metadata.tables["broker_discovered_accounts"],
            Base.metadata.tables["broker_reconciliation_checkpoints"],
        ],
    )


def downgrade() -> None:
    raise RuntimeError("broker account-truth evidence must be retained")
