"""
One-time bootstrap script — creates the first ADMIN user.

Usage:
    uv run python -m app.scripts.create_admin

You only need this ONCE. After the first admin exists, all other
users are created via the invitation flow.
"""

import asyncio
import getpass
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.base import Base
from app.models.role import Role
from app.models.user import User, UserStatus


async def create_admin() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # ── Collect input ────────────────────────────────────────────
        print("\n🔧  CMS Backend — First Admin Setup\n")
        email = input("  Admin email: ").strip()
        full_name = input("  Full name:   ").strip()
        password = getpass.getpass("  Password:    ")
        confirm = getpass.getpass("  Confirm:     ")

        if password != confirm:
            print("\n❌  Passwords do not match.")
            await engine.dispose()
            return

        if not email or not full_name or not password:
            print("\n❌  All fields are required.")
            await engine.dispose()
            return

        # ── Check for existing user ──────────────────────────────────
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        if existing:
            print(f"\n❌  User with email '{email}' already exists.")
            await engine.dispose()
            return

        # ── Find ADMIN role (must be seeded first) ───────────────────
        admin_role = (
            await session.execute(select(Role).where(Role.name == "ADMIN"))
        ).scalar_one_or_none()

        if admin_role is None:
            print("\n❌  ADMIN role not found. Start the app once first so")
            print("   permissions & roles get seeded, then re-run this script.")
            await engine.dispose()
            return

        # ── Create the admin user ────────────────────────────────────
        admin_user = User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            status=UserStatus.ACTIVE,
        )
        admin_user.roles.append(admin_role)
        session.add(admin_user)
        await session.commit()

        print(f"\n✅  Admin user created successfully!")
        print(f"    ID:    {admin_user.id}")
        print(f"    Email: {admin_user.email}")
        print(f"    Role:  ADMIN")
        print(f"\n   You can now log in via POST /api/auth/login\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin())
