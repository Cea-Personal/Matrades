from time import perf_counter

from modules.risk.engine import RiskEngine
from tests.fixtures.pretrade import candidate, context


def test_fixture_pretrade_p95_is_well_below_five_seconds():
    engine = RiskEngine()
    samples = []
    for _ in range(100):
        started = perf_counter()
        engine.evaluate(context(), candidate())
        samples.append(perf_counter() - started)
    assert sorted(samples)[94] < 5


def test_ui_propagation_contract_is_sse():
    assert "text/event-stream" in open("apps/api/app/routes/events.py").read()
