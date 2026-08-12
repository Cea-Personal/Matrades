from traderx.integrations.crypto import SecretBox


def test_encrypted_secrets_are_not_returned_as_plaintext() -> None:
    box = SecretBox("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    encrypted = box.encrypt({"credential": "value"}, aad="integration:1")
    assert "value" not in encrypted.ciphertext_b64
    assert encrypted.key_version == "v1"
    assert box.decrypt(encrypted) == {"credential": "value"}
