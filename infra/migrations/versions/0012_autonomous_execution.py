"""Persist autonomous execution authority while preserving legacy evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)}
    if column.name not in columns:
        op.add_column(table_name, column)


def _create_index_if_missing(name: str, table_name: str, columns: list[str], **kwargs) -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if name not in indexes:
        op.create_index(name, table_name, columns, **kwargs)


def upgrade() -> None:
    if not _has_table("execution_permissions"):
        op.create_table(
            "execution_permissions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("account_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("actions", sa.JSON(), nullable=False),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not _has_table("execution_kill_switches"):
        op.create_table(
            "execution_kill_switches",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("scope", sa.String(16), nullable=False),
            sa.Column("account_id", sa.Uuid(), index=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("safety_epoch", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        )
    # ``risk_reservations`` was introduced by 0002 for legacy proposals. Expand
    # that table in place so historical rows remain readable and new autonomous
    # plans use the same durable capacity ledger.
    _add_column_if_missing("risk_reservations", sa.Column("owner_id", sa.Uuid(), nullable=True))
    _add_column_if_missing(
        "risk_reservations", sa.Column("trade_plan_id", sa.Uuid(), nullable=True)
    )
    _add_column_if_missing("risk_reservations", sa.Column("command_id", sa.Uuid(), nullable=True))
    _add_column_if_missing("risk_reservations", sa.Column("broker_order_id", sa.String(160)))
    _add_column_if_missing("risk_reservations", sa.Column("broker_position_id", sa.String(160)))
    _add_column_if_missing(
        "risk_reservations",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    _add_column_if_missing(
        "risk_reservations",
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    _add_column_if_missing(
        "risk_reservations",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    _add_column_if_missing(
        "risk_reservations",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    proposal = next(
        item
        for item in sa.inspect(op.get_bind()).get_columns("risk_reservations")
        if item["name"] == "proposal_id"
    )
    if not proposal["nullable"]:
        op.alter_column("risk_reservations", "proposal_id", nullable=True)
    _create_index_if_missing(
        "ix_risk_reservations_owner_id", "risk_reservations", ["owner_id"], unique=False
    )
    _create_index_if_missing(
        "ix_risk_reservations_trade_plan_id",
        "risk_reservations",
        ["trade_plan_id"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_risk_reservations_command_id", "risk_reservations", ["command_id"], unique=False
    )
    _create_index_if_missing(
        "ix_risk_reservations_broker_order_id",
        "risk_reservations",
        ["broker_order_id"],
        unique=False,
    )
    _create_index_if_missing(
        "ix_risk_reservations_broker_position_id",
        "risk_reservations",
        ["broker_position_id"],
        unique=False,
    )
    if not _has_table("execution_commands"):
        op.create_table(
            "execution_commands",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("account_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("trade_plan_id", sa.Uuid(), index=True),
            sa.Column("authorization_id", sa.Uuid()),
            sa.Column("action", sa.String(48), nullable=False),
            sa.Column("idempotency_key", sa.String(160), nullable=False),
            sa.Column("state", sa.String(32), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("evidence_refs", sa.JSON(), nullable=False),
            sa.Column("outcome_certainty", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "owner_id", "idempotency_key", name="uq_execution_command_identity"
            ),
            sa.CheckConstraint(
                "length(idempotency_key) >= 8", name="ck_execution_command_idempotency_key"
            ),
        )
    if not _has_table("execution_attempts"):
        op.create_table(
            "execution_attempts",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("command_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(32), nullable=False),
            sa.Column("request_digest", sa.String(64), nullable=False),
            sa.Column("response_digest", sa.String(64)),
            sa.Column("error_code", sa.String(120)),
            sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False),
        )
    # Legacy HIL/proposal/approval rows are intentionally untouched. New API
    # paths use execution_commands and cannot transition those historical rows.


def downgrade() -> None:
    for name in (
        "execution_attempts",
        "execution_commands",
        "execution_kill_switches",
        "execution_permissions",
    ):
        op.drop_table(name)
    for index in (
        "ix_risk_reservations_broker_position_id",
        "ix_risk_reservations_broker_order_id",
        "ix_risk_reservations_command_id",
        "ix_risk_reservations_trade_plan_id",
        "ix_risk_reservations_owner_id",
    ):
        op.drop_index(index, table_name="risk_reservations")
    for column in (
        "updated_at",
        "created_at",
        "details",
        "version",
        "broker_position_id",
        "broker_order_id",
        "command_id",
        "trade_plan_id",
        "owner_id",
    ):
        op.drop_column("risk_reservations", column)
    op.alter_column("risk_reservations", "proposal_id", nullable=False)
