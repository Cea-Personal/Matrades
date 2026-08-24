from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SENSITIVE = re.compile(r"(secret|password|token|api[_-]?key|authorization|credential)", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if SENSITIVE.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(bearer\s+)[\w.\-]+", r"\1[REDACTED]", value)
    return value
