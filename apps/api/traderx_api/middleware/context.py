from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


class ContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        token = correlation_id.set(request_id)
        try:
            response = await call_next(request)  # type: ignore[misc]
            response.headers["X-Correlation-ID"] = request_id
            return response
        finally:
            correlation_id.reset(token)
