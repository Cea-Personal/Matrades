from traderx.notifications.router import retryable, route


def test_critical_notification_has_durable_web_inbox_and_bounded_retries() -> None:
    assert route(severity="CRITICAL", enabled_channels={"email"}).persist_web_inbox
    assert retryable(2)
    assert not retryable(3)
