"""
User service — CRUD & query helpers.

Every query that returns user data must be filtered through the
DataScope so operators never see other warehouses' users and clients
never see other clients.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, UserStatus
from app.rbac.context_resolver import DataScope


async def get_user_by_id(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> User:
    stmt = (
        select(User)
        .options(
            selectinload(User.roles),
            selectinload(User.operator_profile),
            selectinload(User.client),
        )
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def list_users(
    db: AsyncSession,
    scope: DataScope,
    skip: int = 0,
    limit: int = 50,
) -> list[User]:
    """
    List users respecting data scope.

    - Admin: sees all users.
    - Operator: sees users in the same warehouse.
    - Client: sees only themselves.
    """
    stmt = (
        select(User)
        .options(
            selectinload(User.roles),
            selectinload(User.operator_profile),
            selectinload(User.client),
        )
    )

    if scope.is_admin:
        pass  # no filter
    elif scope.warehouse_id:
        # Operator sees only fellow warehouse users
        from app.models.operator_profile import OperatorProfile

        stmt = stmt.join(OperatorProfile, OperatorProfile.user_id == User.id).where(
            OperatorProfile.warehouse_id == scope.warehouse_id
        )
    elif scope.client_id:
        # Client sees only themselves
        stmt = stmt.where(User.id == scope.user_id)
    else:
        # Fallback — only see own record
        stmt = stmt.where(User.id == scope.user_id)

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def disable_user(
    target_user_id: uuid.UUID,
    db: AsyncSession,
) -> User:
    """Admin action — disable a user account and invalidate all sessions."""
    from app.services import session_service

    user = await get_user_by_id(target_user_id, db)
    user.status = UserStatus.DISABLED
    # Immediately invalidate every active session for this user
    await session_service.deactivate_all_user_sessions(target_user_id, db)
    await db.flush()
    return user
