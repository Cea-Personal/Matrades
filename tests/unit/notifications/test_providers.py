import httpx

from modules.notifications.providers import send_notification


async def test_telegram_delivery_uses_bot_api_without_leaking_secret() -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await send_notification(
            "TELEGRAM",
            "bot-secret",
            "1234",
            title="Test",
            message="Hello",
            client=client,
        )
    assert result["status"] == "DELIVERED"
    assert observed[0].url.path.endswith("/sendMessage")
    assert "bot-secret" in str(observed[0].url)
    assert "bot-secret" not in str(result)


async def test_pushover_delivery_uses_application_and_user_keys() -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"status": 1, "request": "receipt"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await send_notification(
            "PUSHOVER",
            "app-token",
            "user-key",
            title="Test",
            message="Hello",
            client=client,
        )
    assert result["status"] == "DELIVERED"
    assert observed[0].url == "https://api.pushover.net/1/messages.json"
    body = observed[0].content.decode()
    assert "token=app-token" in body
    assert "user=user-key" in body
