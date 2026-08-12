from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttachmentMetadata:
    artifact_ref: str
    checksum: str
    classification: str


def checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def superseding_annotation(
    previous_annotation_id: str | None, content: str
) -> dict[str, str | None]:
    if not content.strip():
        raise ValueError("a journal annotation cannot be blank")
    return {"supersedes_id": previous_annotation_id, "content": content}
