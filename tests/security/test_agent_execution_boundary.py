from modules.agents.permissions import PermissionSet


def test_agent_tool_set_contains_only_context_tools():
    permissions = PermissionSet("v1", ("market.read", "knowledge.search"))
    assert not any(
        tool.startswith(("broker.", "order.", "position.")) for tool in permissions.tools
    )
