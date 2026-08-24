from __future__ import annotations

from modules.agents.models import AgentDefinition, RuntimeType

REQUIRED_AGENT_IDS = (
    "orchestrator",
    "forex_research",
    "metals_research",
    "crypto_research",
    "technical_analyst",
    "fundamental_analyst",
    "sentiment_analyst",
    "regime_analyst",
    "strategy_selector",
    "strategy_researcher",
    "strategy_assistant",
    "critic",
    "trade_monitor",
    "journal",
    "performance",
)


class AgentRegistry:
    def __init__(self) -> None:
        self._agents = {
            logical_id: AgentDefinition(logical_id=logical_id) for logical_id in REQUIRED_AGENT_IDS
        }

    def all(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._agents[key] for key in REQUIRED_AGENT_IDS)

    def get(self, logical_id: str) -> AgentDefinition:
        return self._agents[logical_id]

    def configure(self, agent: AgentDefinition) -> None:
        if agent.logical_id not in self._agents:
            raise ValueError("unknown logical agent")
        self._agents[agent.logical_id] = agent

    def remove(self, logical_id: str) -> None:
        if logical_id in REQUIRED_AGENT_IDS:
            raise ValueError("required logical agents cannot be removed")
        self._agents.pop(logical_id, None)


def seed() -> AgentRegistry:
    registry = AgentRegistry()
    assert len(registry.all()) == 15
    assert all(agent.runtime == RuntimeType.CODEX_APP_SERVER for agent in registry.all())
    return registry


if __name__ == "__main__":
    print(f"seeded {len(seed().all())} Codex-default logical agents")
