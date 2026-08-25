from apps.api.app.main import create_app


def test_extras_exposes_archive_folders_and_generated_code() -> None:
    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/extras"]
    assert "get" in paths["/api/v1/extras/overview"]
    assert "get" in paths["/api/v1/extras/cycles"]
    assert "get" in paths["/api/v1/extras/generated-code"]
    assert "get" in paths["/api/v1/extras/generated-code/{strategy_id}"]
    assert "get" in paths["/api/v1/extras/mt5-ea"]
    assert "get" in paths["/api/v1/extras/mt5-ea/download"]


def test_notification_channels_expose_configuration_and_testing() -> None:
    paths = create_app().openapi()["paths"]
    assert "post" in paths["/api/v1/operations/notifications"]
    assert "post" in paths["/api/v1/operations/notification-channels"]
    assert "delete" in paths["/api/v1/operations/notification-channels/{channel_id}"]
    assert "post" in paths["/api/v1/operations/notification-channels/{channel_id}/test"]
    schema = paths["/api/v1/operations/notifications/preferences"]["post"]["requestBody"]
    assert schema["content"]["application/json"]["schema"]


def test_runtime_and_knowledge_expansion_routes_are_in_contract() -> None:
    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/agents/status"]
    assert "get" in paths["/api/v1/agents/runtime-settings"]
    assert "put" in paths["/api/v1/agents/runtime-settings"]
    assert "post" in paths["/api/v1/agents/runtime-settings/test"]
    assert "post" in paths["/api/v1/knowledge/sources/upload"]
    assert "post" in paths["/api/v1/knowledge/youtube/scrape"]
