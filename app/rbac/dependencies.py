"""
RBAC dependencies — the heart of permission enforcement.

`require_permission` is a *dependency factory*:  call it with one or
more permission codes and it returns a FastAPI dependency that will:

1. Decode the JWT (via `get_current_user_token`).
2. Load the full User (with roles → permissions eagerly loaded).
3. Aggregate every permission code the user holds.
4. Verify the required code(s) are present.
5. Return 403 on failure — with NO details about which permissions
   exist (prevents enumeration attacks).

Usage in a route:
    @router.get("/items", dependencies=[Depends(require_permission("inventory.view"))])
    async def list_items(...): ...

Or inject the user object:
    @router.get("/me")
    async def me(user: User = Depends(require_permission("inventory.view"))): ...
"""

import logging
import uuid
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user_token
from app.models.role import Role
from app.models.user import User

logger = logging.getLogger("rbac")


async def _load_user_with_permissions(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> User:
    """Fetch the user and eagerly load roles → permissions in one query."""
    stmt = (
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.operator_profile),
            selectinload(User.client),
        )
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _collect_permission_codes(user: User) -> set[str]:
    """Flatten roles → permissions into a set of code strings."""
    codes: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            codes.add(perm.code)
    return codes


class require_permission:
    """
    Dependency factory.

    Can be used as:
        Depends(require_permission("inventory.view"))
        Depends(require_permission("billing.invoice.create", "billing.invoice.approve"))
    """

    def __init__(self, *permission_codes: str):
        self.required_codes = set(permission_codes)

    async def __call__(
        self,
        token_payload: dict[str, Any] = Depends(get_current_user_token),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        user_id = token_payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        user = await _load_user_with_permissions(uuid.UUID(user_id), db)

        # Disabled users must never pass
        if user.status.value == "DISABLED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account disabled",
            )

        granted = _collect_permission_codes(user)

        if not self.required_codes.issubset(granted):
            logger.warning(
                "Permission denied for user %s — required: %s, granted: %s",
                user.id,
                self.required_codes,
                granted,
            )
            # Intentionally vague — do NOT reveal which codes are missing
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user


async def get_current_active_user(
    token_payload: dict[str, Any] = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency that returns the current user WITHOUT permission checks.
    Useful for routes that only need authentication, not authorization."""
    user_id = token_payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    user = await _load_user_with_permissions(uuid.UUID(user_id), db)
    if user.status.value == "DISABLED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )
    return user
