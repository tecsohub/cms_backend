"""
Shared async test fixtures for audit / ledger tests.

Uses an in-memory SQLite database with async support so tests run
without a real PostgreSQL instance.  JSONB columns fall back to plain
JSON (SQLite compatible) since we only test logic, not Postgres types.
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.product import Product


# ── Engine & session factory (shared across all tests in session) ────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create the async engine once per session."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)

    # SQLite needs PRAGMA foreign_keys = ON per connection
    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    """
    Yield a fresh async session per test.

    Each test runs inside a SAVEPOINT so changes are automatically
    rolled back — no pollution between tests.
    """
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()


# ── Helpers for creating seed data ───────────────────────────────────


async def seed_user(db: AsyncSession, *, email: str = "admin@test.com") -> "User":
    """Insert a minimal User row and return it."""
    from app.models.user import User, UserStatus

    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name="Test User",
        password_hash="fakehash",
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.flush()
    return user


async def seed_warehouse(db: AsyncSession, admin_id: uuid.UUID) -> "Warehouse":
    """Insert a minimal Warehouse row and return it."""
    from app.models.warehouse import Warehouse

    wh = Warehouse(
        id=uuid.uuid4(),
        name="Cold Store A",
        address="123 Frost Lane",
        capacity=1000,
        created_by_admin_id=admin_id,
    )
    db.add(wh)
    await db.flush()
    return wh


async def seed_client(db: AsyncSession, user_id: uuid.UUID, company_name: str = "Test Client") -> "Client":
    """Insert a minimal Client row and return it."""
    from app.models.client import Client

    client = Client(
        id=uuid.uuid4(),
        user_id=user_id,
        company_name=company_name,
    )
    db.add(client)
    await db.flush()
    return client


async def seed_sku(db: AsyncSession, *, warehouse_id: uuid.UUID, created_by: uuid.UUID) -> uuid.UUID:
    """Insert a minimal Product/SKU row and return its UUID."""
    from sqlalchemy import insert

    sku_id = uuid.uuid4()
    await db.execute(
        insert(Product).values(
            id=sku_id,
            name="Test SKU",
            category="FROZEN",
            unit="KG",
            quantity=100.0,
            lot_number="LOT-TEST",
            sku_code=f"TEST-SKU-{sku_id}",
            warehouse_id=warehouse_id,
            created_by=created_by,
        )
    )
    await db.flush()
    return sku_id
