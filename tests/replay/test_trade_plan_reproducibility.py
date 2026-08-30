from modules.risk.engine import RiskEngine
from tests.fixtures.pretrade import candidate, context


def test_trade_plan_risk_replay_is_deterministic() -> None:
    engine, risk_context, trade = RiskEngine(), context(), candidate()
    first = engine.evaluate(risk_context, trade).model_dump()
    second = engine.evaluate(risk_context, trade).model_dump()
    assert first == second
