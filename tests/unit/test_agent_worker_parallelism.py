import asyncio
from types import SimpleNamespace

import pytest

from apps.agent_worker.app import main as worker
from modules.agents.models import RuntimeType
from packages.shared.config import Settings


async def test_four_slots_start_independent_runtimes(monkeypatch) -> None:
    routers = []

    class Router:
        def __init__(self) -> None:
            self.started = False
            self.closed = False
            self.clients = {RuntimeType.CODEX_APP_SERVER: SimpleNamespace(healthy=True)}

        async def start(self) -> None:
            self.started = True

        async def close(self) -> None:
            self.closed = True

    def create(overrides: dict[str, object]) -> Router:
        assert overrides == {"codex_enabled": True}
        router = Router()
        routers.append(router)
        return router

    monkeypatch.setattr(worker.AgentRuntimeRouter, "from_settings", create)
    started = await worker.start_agent_slots({"codex_enabled": True}, 4)

    assert started == routers
    assert len({id(router) for router in started}) == 4
    assert all(router.started for router in started)
    assert worker.codex_slots_healthy(started)
    for router in started:
        await router.close()


async def test_four_agent_requests_can_run_simultaneously(monkeypatch) -> None:
    active = 0
    peak = 0
    all_started = asyncio.Event()
    release = asyncio.Event()

    async def handle(router: object, stopped: asyncio.Event) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 4:
            all_started.set()
        await release.wait()
        active -= 1

    monkeypatch.setattr(worker, "serve_agent_requests", handle)
    routers = [object() for _ in range(4)]
    stopped = asyncio.Event()
    serving = asyncio.create_task(worker.serve_agent_slots(routers, stopped))
    try:
        await asyncio.wait_for(all_started.wait(), timeout=1)
        assert peak == 4
    finally:
        release.set()
        await serving


async def test_failed_slot_start_closes_started_runtime(monkeypatch) -> None:
    routers = []

    class Router:
        def __init__(self, fail: bool) -> None:
            self.fail = fail
            self.closed = False

        async def start(self) -> None:
            if self.fail:
                raise RuntimeError("startup failed")

        async def close(self) -> None:
            self.closed = True

    def create(overrides: dict[str, object]) -> Router:
        router = Router(fail=len(routers) == 1)
        routers.append(router)
        return router

    monkeypatch.setattr(worker.AgentRuntimeRouter, "from_settings", create)
    with pytest.raises(RuntimeError, match="startup failed"):
        await worker.start_agent_slots({}, 4)
    assert len(routers) == 2
    assert all(router.closed for router in routers)


def test_agent_slot_limit_is_bounded() -> None:
    assert Settings(_env_file=None, agent_worker_concurrency=4).agent_worker_concurrency == 4
    with pytest.raises(ValueError):
        Settings(_env_file=None, agent_worker_concurrency=0)
    with pytest.raises(ValueError):
        Settings(_env_file=None, agent_worker_concurrency=9)
