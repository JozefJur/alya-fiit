"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.routers import admin, auth, cart, catalog, meta, orders, payments, support, warehouse
from app.config import get_settings
from app.infrastructure.persistence.database import create_schema


def create_app(*, init_schema: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if init_schema:
            create_schema()
        yield

    app = FastAPI(
        title="Alya-FIIT",
        version="1.0.0",
        description="Alya-FIIT e-shop and warehouse back office.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    for module in (auth, catalog, cart, orders, payments, warehouse, support, admin, meta):
        app.include_router(module.router)

    return app


app = create_app()
