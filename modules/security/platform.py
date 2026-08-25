from __future__ import annotations

import ipaddress
from collections import defaultdict, deque
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse

ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/vtt",
    "application/x-subrip",
}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def validate_csrf(cookie_token: str | None, header_token: str | None) -> None:
    if not cookie_token or not header_token or cookie_token != header_token:
        raise PermissionError("CSRF validation failed")


def validate_upload(name: str, content_type: str, size: int) -> None:
    if (
        content_type not in ALLOWED_UPLOAD_TYPES
        or size > MAX_UPLOAD_BYTES
        or Path(name).suffix.lower() not in {".pdf", ".docx", ".txt", ".md", ".vtt", ".srt"}
    ):
        raise ValueError("unsafe upload")


def validate_outbound_url(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username
        or parsed.password
    ):
        raise ValueError("outbound URL not permitted")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        if address.is_private or address.is_loopback or address.is_link_local:
            raise ValueError("private network targets forbidden")
    except ValueError as exc:
        if "forbidden" in str(exc):
            raise
    return url


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self.items = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = monotonic()
        values = self.items[key]
        while values and now - values[0] > self.window:
            values.popleft()
        if len(values) >= self.limit:
            return False
        values.append(now)
        return True
