import pytest

from modules.security.platform import (
    RateLimiter,
    validate_csrf,
    validate_outbound_url,
    validate_upload,
)


def test_csrf_rate_upload_and_ssrf_guards():
    with pytest.raises(PermissionError):
        validate_csrf("a", "b")
    limiter = RateLimiter(1, 60)
    assert limiter.allow("owner")
    assert not limiter.allow("owner")
    with pytest.raises(ValueError):
        validate_upload("evil.exe", "application/octet-stream", 1)
    with pytest.raises(ValueError):
        validate_outbound_url("http://127.0.0.1/admin", {"127.0.0.1"})
