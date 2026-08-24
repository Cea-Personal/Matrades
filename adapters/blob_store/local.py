from __future__ import annotations

from pathlib import Path
from uuid import UUID


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, owner_id: UUID, key: str) -> Path:
        safe_key = Path(key)
        if safe_key.is_absolute() or ".." in safe_key.parts:
            raise ValueError("unsafe blob key")
        path = (self.root / str(owner_id) / safe_key).resolve()
        if self.root not in path.parents:
            raise ValueError("unsafe blob key")
        return path

    def put(self, owner_id: UUID, key: str, body: bytes) -> None:
        path = self._path(owner_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def get(self, owner_id: UUID, key: str) -> bytes:
        return self._path(owner_id, key).read_bytes()
