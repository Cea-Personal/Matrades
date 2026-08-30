from time import perf_counter

from modules.risk.engine import RiskEngine
from tests.fixtures.pretrade import candidate, context


def test_candidate_evaluation_slo() -> None:
    started = perf_counter()
    RiskEngine().evaluate(context(), candidate())
    assert perf_counter() - started < 5
