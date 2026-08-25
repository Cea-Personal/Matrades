from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from apps.api.app.errors import install_error_handlers
from apps.api.app.routes import api_router
from packages.shared.database import engine
from packages.shared.persistence import Base

logging.getLogger("httpx").setLevel(logging.WARNING)


def database_lifespan(database_engine: AsyncEngine):
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with database_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield
        await database_engine.dispose()

    return lifespan


def create_app(database_engine: AsyncEngine = engine) -> FastAPI:
    app = FastAPI(
        title="Matrades API",
        version="0.1.0",
        description="Human-controlled, Codex-first trading decision support",
        lifespan=database_lifespan(database_engine),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(api_router)

    @app.get("/version", tags=["Operations"])
    async def version() -> dict[str, str]:
        return {"name": "matrades", "version": app.version}

    return app


app = create_app()
