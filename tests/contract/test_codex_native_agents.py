from pathlib import Path
import tomllib

from modules.agents.registry import REQUIRED_AGENT_IDS


ROOT = Path(__file__).parents[2]
NATIVE_AGENT_DIR = ROOT / ".codex" / "agents"


def test_project_defines_one_read_only_native_agent_for_each_logical_role():
    definitions = {}
    for path in sorted(NATIVE_AGENT_DIR.glob("*.toml")):
        with path.open("rb") as stream:
            definitions[path.stem] = tomllib.load(stream)

    assert set(definitions) == set(REQUIRED_AGENT_IDS)
    assert all(
        definition["name"] == logical_id
        and definition["description"].strip()
        and definition["developer_instructions"].strip()
        and definition["sandbox_mode"] == "read-only"
        for logical_id, definition in definitions.items()
    )


def test_native_subagents_are_enabled_for_the_project():
    with (ROOT / ".codex" / "config.toml").open("rb") as stream:
        config = tomllib.load(stream)

    assert config["agents"]["enabled"] is True
    assert config["agents"]["max_concurrent_threads_per_session"] == 8
