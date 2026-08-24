from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class StoredResult(Generic[T]):  # noqa: UP046 - retain Python 3.11-compatible typing form
    request_hash: str
    value: T


class IdempotencyStore(Generic[T]):  # noqa: UP046 - retain Python 3.11-compatible typing form
    """Process-local development store; production repositories use the same semantics."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], StoredResult[T]] = {}
        self._lock = Lock()

    @staticmethod
    def digest(body: bytes) -> str:
        return sha256(body).hexdigest()

    def remember(self, owner: str, key: str, body: bytes, value: T) -> T:
        identity = (owner, key)
        digest = self.digest(body)
        with self._lock:
            prior = self._values.get(identity)
            if prior and prior.request_hash != digest:
                raise ValueError("idempotency key reused with a different request")
            if prior:
                return prior.value
            self._values[identity] = StoredResult(digest, value)
            return value
