from time import perf_counter

from modules.research.matrix import ALL_LANES
from modules.risk.engine import RiskEngine
from tests.fixtures.pretrade import candidate, context


def test_platform_slo_probes_are_bounded() -> None:
    started = perf_counter()
    for _ in range(25):
        RiskEngine().evaluate(context(), candidate())
    assert perf_counter() - started < 5
    assert len(ALL_LANES) == 12
