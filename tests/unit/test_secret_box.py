import base64
import os

from traderx.integrations.crypto import SecretBox, redact


def test_secret_box_round_trip_and_redaction() -> None:
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    box = SecretBox(key)
    encrypted = box.encrypt({"api_token": "secret"}, aad="credential:1")
    assert box.decrypt(encrypted) == {"api_token": "secret"}
    assert redact({"api_token": "secret"}) == {"api_token": "***"}
