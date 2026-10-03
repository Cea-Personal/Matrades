import pytest
from pydantic import SecretStr

from modules.identity import email_delivery
from packages.shared.config import Settings


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        env="production",
        public_app_url="https://matrades.example",
        smtp_host="smtp.example",
        smtp_username="mailer",
        smtp_password=SecretStr("mail-secret"),
        smtp_from="auth@matrades.example",
    )


def test_public_auth_email_requires_https_and_authenticated_relay() -> None:
    assert email_delivery.delivery_mode(_settings()) == "SMTP"
    with pytest.raises(email_delivery.AuthEmailUnavailable):
        email_delivery.delivery_mode(
            _settings().model_copy(update={"public_app_url": "http://matrades.example"})
        )
    with pytest.raises(email_delivery.AuthEmailUnavailable):
        email_delivery.delivery_mode(_settings().model_copy(update={"smtp_password": None}))
    with pytest.raises(email_delivery.AuthEmailUnavailable):
        email_delivery.delivery_mode(
            _settings().model_copy(update={"public_app_url": "https://matrades.example/other"})
        )
    with pytest.raises(email_delivery.AuthEmailUnavailable):
        email_delivery.delivery_mode(
            _settings().model_copy(update={"public_app_url": "https://[broken"})
        )
    assert (
        email_delivery.delivery_mode(
            _settings().model_copy(update={"auth_dev_tokens_enabled": True})
        )
        == "SMTP"
    )


async def test_token_is_returned_only_for_explicit_development_mode(monkeypatch) -> None:
    local = Settings(_env_file=None, env="development", auth_dev_tokens_enabled=True)
    monkeypatch.setattr(email_delivery, "get_settings", lambda: local)
    assert (
        await email_delivery.deliver_auth_link("owner@example.com", "verify", "secret-token")
        == "secret-token"
    )


async def test_bad_sender_configuration_is_reported_as_delivery_unavailable(monkeypatch) -> None:
    configured = _settings().model_copy(update={"smtp_from": "bad\nSender: injected"})
    monkeypatch.setattr(email_delivery, "get_settings", lambda: configured)
    with pytest.raises(email_delivery.AuthEmailUnavailable):
        await email_delivery.deliver_auth_link("owner@example.com", "verify", "secret-token")
