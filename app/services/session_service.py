"""
Session service — CRUD & lifecycle helpers for user sessions.

Handles:
- Querying active sessions (for concurrency checks)
- Deactivating single sessions (logout)
- Deactivating all sessions for a user (force logout / disable)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import UserSession


async def get_active_sessions(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[UserSession]:
    """Return all active sessions for a user."""
    stmt = select(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_active_session_by_id(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> UserSession | None:
    """Return a single active session by its primary key."""
    stmt = select(UserSession).where(
        UserSession.id == session_id,
        UserSession.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def deactivate_session(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Mark a single session as inactive (logout)."""
    stmt = (
        update(UserSession)
        .where(UserSession.id == session_id)
        .values(is_active=False)
    )
    await db.execute(stmt)
    await db.flush()


async def deactivate_all_user_sessions(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    Deactivate every active session for a given user.

    Returns the number of sessions affected.
    Used by admin force-logout and user disable flows.
    """
    stmt = (
        update(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.is_active == True,  # noqa: E712
        )
        .values(is_active=False)
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount
