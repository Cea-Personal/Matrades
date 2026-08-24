from modules.agents.models import RuntimeType
from modules.agents.runtime import AgentRuntimeRouter
from modules.knowledge.authority import RecordAuthority, route
from modules.risk.engine import RiskEngine
from tests.fixtures.pretrade import candidate, context


def test_authority_outages_fail_safe_without_cross_runtime():
    assert RiskEngine().evaluate(context(), candidate()).decision == "PASS"
    assert AgentRuntimeRouter().clients == {}
    assert route("knowledge") == RecordAuthority.CONTEXT_ONLY
    assert RuntimeType.LITELLM_GATEWAY not in AgentRuntimeRouter().clients


def test_zero_remaining_capacity_blocks():
    ctx = context()
    ctx = ctx.model_copy(update={"static_max_concurrent_trades": 0})
    assert RiskEngine().evaluate(ctx, candidate()).decision == "HARD_BLOCK"
