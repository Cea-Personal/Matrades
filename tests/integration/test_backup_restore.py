import base64
import os

from traderx.integrations.crypto import SecretBox


def test_encrypted_backup_payload_restores_with_authenticated_envelope() -> None:
    box = SecretBox(base64.urlsafe_b64encode(os.urandom(32)).decode())
    envelope = box.encrypt({"backup": "manifest"}, aad="backup:1")
    assert box.decrypt(envelope) == {"backup": "manifest"}
