from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from traderx.shared.config import get_settings
from traderx.shared.db import load_model_metadata
from traderx.shared.types import DomainError
from traderx_api.middleware.context import ContextMiddleware
from traderx_api.middleware.problems import domain_error_handler
from traderx_api.routes.accounts import router as accounts_router
from traderx_api.routes.approvals import router as approvals_router
from traderx_api.routes.dashboard import router as dashboard_router
from traderx_api.routes.health import router as health_router
from traderx_api.routes.identity import router as identity_router
from traderx_api.routes.identity import user_router as identity_user_router
from traderx_api.routes.integrations import router as integrations_router
from traderx_api.routes.jobs import router as jobs_router
from traderx_api.routes.journal import router as journal_router
from traderx_api.routes.market_rotation import router as market_rotation_router
from traderx_api.routes.markets import calendar_router, router as markets_router
from traderx_api.routes.notifications import router as notifications_router
from traderx_api.routes.operations import router as operations_router
from traderx_api.routes.opportunities import router as opportunities_router
from traderx_api.routes.paper import router as paper_router
from traderx_api.routes.positions import router as positions_router
from traderx_api.routes.strategies import research_router
from traderx_api.routes.strategies import router as strategies_router
from traderx_api.routes.validation import router as validation_router

load_model_metadata()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings().validate_startup()
    yield


app = FastAPI(
    title="TraderX Core Platform API",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    lifespan=lifespan,
)
app.add_middleware(ContextMiddleware)
app.add_exception_handler(DomainError, domain_error_handler)
app.include_router(health_router, prefix="/api/v1")
app.include_router(identity_router, prefix="/api/v1")
app.include_router(identity_user_router, prefix="/api/v1")
app.include_router(accounts_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(markets_router, prefix="/api/v1")
app.include_router(calendar_router, prefix="/api/v1")
app.include_router(strategies_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(validation_router, prefix="/api/v1")
app.include_router(paper_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")
app.include_router(opportunities_router, prefix="/api/v1")
app.include_router(positions_router, prefix="/api/v1")
app.include_router(journal_router, prefix="/api/v1")
app.include_router(market_rotation_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(operations_router, prefix="/api/v1")
