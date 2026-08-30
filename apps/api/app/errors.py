from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    def __init__(
        self, code: str, message: str, *, status: int = 400, details: dict | None = None
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details or {}


EXECUTION_ERROR_STATUS = {
    "STALE_AUTHORITY": 409,
    "ACTION_DISABLED": 403,
    "KILL_SWITCH_ACTIVE": 423,
    "COMMAND_CONFLICT": 409,
    "OUTCOME_UNKNOWN": 202,
}


def execution_error(code: str, message: str, *, details: dict | None = None) -> DomainError:
    """Map deterministic execution failures to stable, machine-readable API errors."""
    normalized = code.upper()
    return DomainError(
        normalized,
        message,
        status=EXECUTION_ERROR_STATUS.get(normalized, 409),
        details=details,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )
