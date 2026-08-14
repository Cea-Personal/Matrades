from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True, slots=True)
class EncryptedSecret:
    ciphertext_b64: str
    nonce_b64: str
    key_version: str
    aad: str
    wrapped_dek_b64: str | None = None
    dek_nonce_b64: str | None = None


class SecretBox:
    def __init__(self, key_b64: str, key_version: str = "v1") -> None:
        self._key = base64.urlsafe_b64decode(key_b64)
        if len(self._key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self._key_version = key_version

    def encrypt(self, value: dict[str, object], *, aad: str) -> EncryptedSecret:
        data_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        encrypted = AESGCM(data_key).encrypt(
            nonce, json.dumps(value, sort_keys=True).encode(), aad.encode()
        )
        dek_nonce = os.urandom(12)
        wrapped_dek = AESGCM(self._key).encrypt(dek_nonce, data_key, aad.encode())
        return EncryptedSecret(
            ciphertext_b64=base64.urlsafe_b64encode(encrypted).decode(),
            nonce_b64=base64.urlsafe_b64encode(nonce).decode(),
            key_version=self._key_version,
            aad=aad,
            wrapped_dek_b64=base64.urlsafe_b64encode(wrapped_dek).decode(),
            dek_nonce_b64=base64.urlsafe_b64encode(dek_nonce).decode(),
        )

    def decrypt(self, secret: EncryptedSecret) -> dict[str, object]:
        data_key = self._key
        if secret.wrapped_dek_b64 is not None and secret.dek_nonce_b64 is not None:
            data_key = AESGCM(self._key).decrypt(
                base64.urlsafe_b64decode(secret.dek_nonce_b64),
                base64.urlsafe_b64decode(secret.wrapped_dek_b64),
                secret.aad.encode(),
            )
        plaintext = AESGCM(data_key).decrypt(
            base64.urlsafe_b64decode(secret.nonce_b64),
            base64.urlsafe_b64decode(secret.ciphertext_b64),
            secret.aad.encode(),
        )
        return json.loads(plaintext)


def redact(value: object) -> object:
    sensitive = {"password", "secret", "token", "key", "authorization", "credential"}
    if isinstance(value, dict):
        return {
            k: ("***" if any(word in k.lower() for word in sensitive) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
