from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from traderx.shared.types import DomainError
from traderx_api.middleware.context import correlation_id


async def domain_error_handler(request: Request, error: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        media_type="application/problem+json",
        content={
            "type": f"/problems/{error.code}",
            "title": error.code.replace("_", " ").title(),
            "status": error.status_code,
            "detail": error.detail,
            "instance": str(request.url.path),
            "code": error.code,
            "correlation_id": correlation_id.get(),
            "field_errors": error.fields,
        },
    )
