from modules.trading.execution import ExecutionService
from tests.unit.test_execution_service import make_plan, permissions, switches


def test_trade_plan_authorization_and_read_model_fields_are_explicit():
    plan = make_plan()
    authorization = ExecutionService().authorize(plan, permissions(plan.account_id), *switches())
    command = ExecutionService().create_command(
        plan, authorization, idempotency_key="contract-1234"
    )

    assert authorization.account_id == plan.account_id
    assert command.trade_plan_id == plan.id
    assert command.idempotency_key == "contract-1234"
