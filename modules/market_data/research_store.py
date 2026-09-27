"""Content-addressed, owner-isolated raw, normalized and feature archives."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from uuid import UUID


class ResearchDataStore:
    def __init__(self, root: Path, owner_id: UUID):
        self.root = root / str(owner_id)

    def put(self, payload: bytes, *, layer: str, extension: str) -> dict:
        if layer not in {"raw", "normalized", "features", "experiments"}:
            raise ValueError("unsupported research archive layer")
        if extension not in {"json", "bi5", "parquet"}:
            raise ValueError("unsupported archive format")
        checksum = hashlib.sha256(payload).hexdigest()
        directory = self.root / layer
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{checksum}.{extension}"
        if not target.exists():
            descriptor, temporary = tempfile.mkstemp(dir=directory)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    pass  # Another job archived identical content, never overwrite it.
            finally:
                Path(temporary).unlink(missing_ok=True)
        return {"layer": layer, "checksum": checksum, "extension": extension, "bytes": len(payload)}

    def get(self, reference: dict) -> bytes:
        checksum = str(reference["checksum"])
        if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
            raise ValueError("invalid archive checksum")
        layer, extension = reference["layer"], reference["extension"]
        if layer not in {"raw", "normalized", "features", "experiments"} or extension not in {
            "json",
            "bi5",
            "parquet",
        }:
            raise ValueError("invalid archive reference")
        payload = (self.root / layer / f"{checksum}.{extension}").read_bytes()
        if hashlib.sha256(payload).hexdigest() != checksum:
            raise ValueError("research archive integrity failure")
        return payload

    def json(self, value: object, *, layer: str = "raw") -> dict:
        return self.put(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
            layer=layer,
            extension="json",
        )

    def frame(self, value, *, layer: str = "normalized") -> dict:
        return self.put(value.to_parquet(index=True), layer=layer, extension="parquet")

    def read_frame(self, reference: dict):
        import io

        import pandas as pd

        return pd.read_parquet(io.BytesIO(self.get(reference)))
