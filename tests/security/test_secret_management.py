import logging

from traderx.integrations.crypto import SecretBox, redact
from traderx.shared.observability import TelemetryEvent, emit


def test_encrypted_secrets_are_not_returned_as_plaintext() -> None:
    box = SecretBox("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    encrypted = box.encrypt({"credential": "value"}, aad="integration:1")
    assert "value" not in encrypted.ciphertext_b64
    assert encrypted.wrapped_dek_b64 is not None
    assert encrypted.dek_nonce_b64 is not None
    assert encrypted.key_version == "v1"
    assert box.decrypt(encrypted) == {"credential": "value"}


def test_secret_redaction_covers_nested_logs_and_telemetry(caplog) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "authorization": "Bearer private",
        "nested": [{"bot_token": "private", "safe": "visible"}],
    }
    assert redact(payload) == {
        "authorization": "***",
        "nested": [{"bot_token": "***", "safe": "visible"}],
    }
    with caplog.at_level(logging.INFO, logger="traderx"):
        emit(TelemetryEvent("credential.rotation", "correlation", payload))
    assert "private" not in caplog.text
    assert "visible" in caplog.text
