import asyncio

from modules.agents.models import AgentDefinition, ModelProfile, RuntimeType
from modules.agents.permissions import PermissionSet
from modules.agents.prompts import ResolvedPrompts
from modules.agents.runtime import AgentRuntimeRouter


class Client:
    def __init__(self):
        self.calls = 0

    async def invoke(self, payload):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("model unavailable")
        return {"ok": True}


def test_same_runtime_fallback_and_audit():
    async def run():
        first = ModelProfile(
            name="a",
            runtime=RuntimeType.CODEX_APP_SERVER,
            provider="openai",
            model="a",
            fallback_profile_ids=[],
        )
        fallback = ModelProfile(
            name="b", runtime=RuntimeType.CODEX_APP_SERVER, provider="openai", model="b"
        )
        first = first.model_copy(update={"fallback_profile_ids": [fallback.id]})
        agent = AgentDefinition(logical_id="critic", profile_id=first.id)
        router = AgentRuntimeRouter({RuntimeType.CODEX_APP_SERVER: Client()})
        execution, result = await router.execute(
            agent,
            {first.id: first, fallback.id: fallback},
            ResolvedPrompts("s", "u", "platform", "platform"),
            PermissionSet("v1", ("market.read",)),
            {},
        )
        assert result == {"ok": True}
        assert execution.actual_runtime == RuntimeType.CODEX_APP_SERVER
        assert execution.actual_model == "b"

    asyncio.run(run())
