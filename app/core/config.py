"""
Application configuration.

All settings are loaded from environment variables (or a .env file).
Pydantic-settings validates and types every value at startup, so
misconfiguration fails fast instead of at runtime.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "CMS Backend"
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────────────────
    # Async driver for runtime; sync URL derived automatically for
    # migrations / seed scripts.
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cms_db"

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Replace the async driver with a sync one for Alembic / seeds."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")

    # ── JWT / Auth ───────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE-ME-in-production-use-a-real-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Email / SMTP ─────────────────────────────────────────────────
    EMAIL_HOST: str = "smtp.gmail.com"
    EMAIL_PORT: int = 587
    SENDER_EMAIL: str = ""
    EMAIL_PASSWORD: str = ""

    # ── Frontend ─────────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
