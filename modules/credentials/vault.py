from __future__ import annotations

import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from modules.credentials.models import CredentialVersion


@dataclass(frozen=True)
class EncryptedEnvelope:
    ciphertext: str
    nonce: str
    wrapped_key: str
    wrap_nonce: str
    key_version: str

    def as_dict(self) -> dict[str, str]:
        return self.__dict__.copy()


class EnvelopeCipher:
    """Envelope encryption with a replaceable key-encryption boundary."""

    def __init__(self, key_encryption_key: bytes, key_version: str = "local-v1") -> None:
        self.key_encryption_key = sha256(key_encryption_key).digest()
        self.key_version = key_version

    def encrypt(self, owner_id: UUID, secret: str) -> EncryptedEnvelope:
        data_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        wrap_nonce = os.urandom(12)
        aad = str(owner_id).encode()
        ciphertext = AESGCM(data_key).encrypt(nonce, secret.encode(), aad)
        wrapped_key = AESGCM(self.key_encryption_key).encrypt(wrap_nonce, data_key, aad)
        return EncryptedEnvelope(
            ciphertext=urlsafe_b64encode(ciphertext).decode(),
            nonce=urlsafe_b64encode(nonce).decode(),
            wrapped_key=urlsafe_b64encode(wrapped_key).decode(),
            wrap_nonce=urlsafe_b64encode(wrap_nonce).decode(),
            key_version=self.key_version,
        )

    def decrypt(self, owner_id: UUID, envelope: dict[str, str]) -> str:
        aad = str(owner_id).encode()
        data_key = AESGCM(self.key_encryption_key).decrypt(
            urlsafe_b64decode(envelope["wrap_nonce"]),
            urlsafe_b64decode(envelope["wrapped_key"]),
            aad,
        )
        return (
            AESGCM(data_key)
            .decrypt(
                urlsafe_b64decode(envelope["nonce"]),
                urlsafe_b64decode(envelope["ciphertext"]),
                aad,
            )
            .decode()
        )


class CredentialVault:
    def __init__(self, master_key: bytes, key_version: str = "v1"):
        if len(master_key) not in (16, 24, 32):
            raise ValueError("AES master key must be 16, 24, or 32 bytes")
        self.key, self.key_version, self._items = master_key, key_version, {}

    def store(self, owner_id: UUID, name: str, secret: str) -> CredentialVersion:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, secret.encode(), str(owner_id).encode())
        item = CredentialVersion(
            owner_id=owner_id,
            name=name,
            ciphertext=ciphertext,
            nonce=nonce,
            key_version=self.key_version,
            masked_hint=("•" * max(4, len(secret) - 4)) + secret[-4:],
        )
        self._items[item.id] = item
        return item

    def resolve_for_adapter(self, owner_id: UUID, credential_id: UUID) -> str:
        item = self._items[credential_id]
        if item.owner_id != owner_id or not item.active:
            raise PermissionError("credential unavailable")
        return (
            AESGCM(self.key).decrypt(item.nonce, item.ciphertext, str(owner_id).encode()).decode()
        )

    def public(self, item: CredentialVersion) -> dict:
        return {
            "id": item.id,
            "name": item.name,
            "masked_hint": item.masked_hint,
            "key_version": item.key_version,
            "active": item.active,
        }

    def delete(self, owner_id: UUID, credential_id: UUID) -> None:
        if self._items[credential_id].owner_id != owner_id:
            raise PermissionError
        del self._items[credential_id]
