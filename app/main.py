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

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Register routers ─────────────────────────────────────────────
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(operator_router)
    app.include_router(client_router)

    # ── Startup / Shutdown ───────────────────────────────────────────
    @app.on_event("startup")
    async def on_startup() -> None:
        """Seed permissions & roles on startup.

        NOTE: Database schema is managed by Alembic migrations.
        Run `alembic upgrade head` before starting the app.
        """
        # Auto-seed permissions & roles (idempotent)
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.rbac.permission_seed import seed

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            await seed(session)
        logger.info("Permission seed complete.")

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await engine.dispose()
        logger.info("Database engine disposed.")

    # ── Health check ─────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
