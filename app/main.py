"""
FastAPI application factory.

Assembles the app, registers all routers, and wires up lifecycle
events.  Database schema is managed by Alembic — NOT create_all.
"""

import logging

from fastapi import FastAPI

from app.controllers.admin_controller import router as admin_router
from app.controllers.auth_controller import router as auth_router
from app.controllers.client_controller import router as client_router
from app.controllers.operator_controller import router as operator_router
from app.core.config import settings
from app.core.database import engine
from app.models import Base  # noqa: F401 — ensures all models are registered

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    # ── Startup / Shutdown ───────────────────────────────────────────
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup — seeding is handled separately via:
        #   python -m app.rbac.permission_seed
        yield

        # Shutdown
        await engine.dispose()
        logger.info("Database engine disposed.")

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Register routers ─────────────────────────────────────────────
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(operator_router)
    app.include_router(client_router)

    # ── Health check ─────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
