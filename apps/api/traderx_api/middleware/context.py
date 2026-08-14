from __future__ import annotations

from contextvars import ContextVar
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from traderx.shared.observability import metrics, traced_operation

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


class ContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        token = correlation_id.set(request_id)
        try:
            if request.method not in {"GET", "HEAD", "OPTIONS"} and not _same_origin(request):
                response = JSONResponse(
                    status_code=403,
                    content={
                        "type": "https://traderx.local/problems/cross-origin-request",
                        "title": "Cross-origin request denied",
                        "status": 403,
                        "detail": "state-changing browser requests must originate from this TraderX host",
                        "code": "cross_origin_request_denied",
                    },
                    headers={"X-Correlation-ID": request_id},
                    media_type="application/problem+json",
                )
                return _secure_response(response)
            with traced_operation(
                "http.request",
                correlation_id=request_id,
                attributes={"method": request.method, "path": request.url.path},
            ):
                response = await call_next(request)  # type: ignore[misc]
            metrics.increment(f"http.status.{response.status_code}")
            response.headers["X-Correlation-ID"] = request_id
            return _secure_response(response)
        finally:
            correlation_id.reset(token)


def _same_origin(request: Request) -> bool:
    fetch_site = request.headers.get("Sec-Fetch-Site", "").lower()
    if fetch_site == "cross-site":
        return False
    origin = request.headers.get("Origin")
    if not origin:
        # Non-browser MT5 and server clients do not send Origin. Their narrow
        # bearer-authenticated routes retain their own authorization boundary.
        return True
    parsed = urlsplit(origin)
    return parsed.netloc.lower() == request.headers.get("host", "").lower()


def _secure_response(response: Response) -> Response:
    # Preserve stricter resource-level directives such as protected journal
    # evidence's ``private, no-store`` policy.
    if "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response
