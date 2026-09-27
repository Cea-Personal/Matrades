"""The registry and runtime share fresh native defaults and owner-scoped overrides."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.agents.configuration import load_agents, load_profiles, native_profile
from modules.agents.models import AgentDefinition, ModelProfile, RuntimeType
from modules.agents.registry import REQUIRED_AGENT_IDS
from packages.shared.persistence import Base
from packages.shared.store import ResourceStore


async def test_saved_agent_configuration_and_profiles_never_cross_owners() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, other_owner = uuid4(), uuid4()
    profile = ModelProfile(
        name="Explicit override",
        runtime=RuntimeType.CODEX_APP_SERVER,
        provider="openai",
        model="configured-model",
        parameters={"reasoning_effort": "high", "assignment": "native_agent"},
    )
    agent = AgentDefinition(
        logical_id="critic",
        profile_id=profile.id,
        system_prompt_override="Bounded custom critic",
        permission_set_version="custom-v2",
    )
    try:
        async with factory() as session:
            store = ResourceStore(session)
            saved_profile = await store.create(
                "agent_profile", owner, profile.model_dump(mode="json")
            )
            await store.create("agent_configuration", owner, agent.model_dump(mode="json"))
            await session.commit()

            profiles = await load_profiles(store, owner)
            agents = await load_agents(store, owner)
            assert profiles[profile.id].model == "configured-model"
            assert profiles[profile.id].parameters == {
                "reasoning_effort": "high",
                "assignment": "agent_profile",
            }
            assert agents["critic"] == agent
            assert set(agents) == set(REQUIRED_AGENT_IDS)
            for logical_id in REQUIRED_AGENT_IDS:
                default = native_profile(logical_id)
                assert profiles[default.id] == default
            assert saved_profile.data["parameters"]["assignment"] == "native_agent"

            other_profiles = await load_profiles(store, other_owner)
            other_agents = await load_agents(store, other_owner)
            assert profile.id not in other_profiles
            assert other_agents["critic"].profile_id is None
            assert other_agents["critic"].system_prompt_override is None
            assert other_agents["critic"].permission_set_version == "v1"
    finally:
        await engine.dispose()


async def test_configuration_is_reloaded_without_reusing_saved_profile_snapshots() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            owner = uuid4()
            store = ResourceStore(session)
            native = native_profile("critic")
            saved = await store.create(
                "agent_profile",
                owner,
                native.model_copy(update={"model": "first-model"}).model_dump(mode="json"),
            )
            first = await load_profiles(store, owner)
            await store.update(saved, {**saved.data, "model": "updated-model"})
            second = await load_profiles(store, owner)
            assert first[native.id].model == "first-model"
            assert second[native.id].model == "updated-model"
            assert second[native.id].parameters["assignment"] == "agent_profile"
    finally:
        await engine.dispose()
