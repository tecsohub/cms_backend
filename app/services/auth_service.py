"""
Authentication service.

Handles:
- Login (email + password → JWT)
- Token payload construction (includes role_ids, warehouse_id, client_id)
- Invitation acceptance (set password, activate account)

All business logic lives here — controllers call service methods
and return the result.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, hash_password, verify_password
from app.models.invitation import Invitation, InvitationStatus
from app.models.role import Role
from app.models.user import User, UserStatus


async def authenticate_user(email: str, password: str, db: AsyncSession) -> dict:
    """
    Validate credentials and return a JWT access token.

    The token payload carries contextual IDs so downstream middleware
    and services can resolve data scope without extra DB queries on
    every request.
    """
    stmt = (
        select(User)
        .options(
            selectinload(User.roles),
            selectinload(User.operator_profile),
            selectinload(User.client),
        )
        .where(User.email == email)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.status == UserStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # ── Build JWT payload ────────────────────────────────────────────
    payload: dict = {
        "user_id": str(user.id),
        "role_ids": [str(r.id) for r in user.roles],
        "role_names": [r.name for r in user.roles],
    }

    # Contextual IDs for data-scope resolution
    if user.operator_profile:
        payload["warehouse_id"] = str(user.operator_profile.warehouse_id)
    if user.client:
        payload["client_id"] = str(user.client.id)

    token = create_access_token(payload)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": str(user.id),
        "roles": payload["role_names"],
    }


async def accept_invitation(
    token: str,
    password: str,
    full_name: str,
    warehouse_id: uuid.UUID | None,
    db: AsyncSession,
) -> User:
    """
    Accept an invitation: validate the token, create/activate the user,
    assign the designated role.
    """
    stmt = select(Invitation).where(
        Invitation.token == token,
        Invitation.status == InvitationStatus.PENDING,
    )
    result = await db.execute(stmt)
    invite = result.scalar_one_or_none()

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation",
        )

    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = InvitationStatus.EXPIRED
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    # Find or create user
    user_stmt = (
        select(User)
        .options(selectinload(User.roles))
        .where(User.email == invite.email)
    )
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=invite.email,
            full_name=full_name,
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user, ["roles"])
    else:
        user.password_hash = hash_password(password)
        user.full_name = full_name
        user.status = UserStatus.ACTIVE

    # Assign role
    role_stmt = select(Role).where(Role.name == invite.role_assigned)
    role_result = await db.execute(role_stmt)
    role = role_result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Assigned role does not exist",
        )
    if role not in user.roles:
        user.roles.append(role)

    if role.name == "OPERATOR":
        # For operator invites, we also need to set the warehouse_id in the JWT payload.
        # This is a bit of a special case since we have a separate OperatorProfile
        # table. The warehouse_id will be selected by operator while accepting the invite, so we create the OperatorProfile here with a null warehouse_id, and update it later when the operator selects their warehouse.
        from app.models.operator_profile import OperatorProfile
        profile = OperatorProfile(user_id=user.id, warehouse_id=warehouse_id)
        db.add(profile)

    invite.status = InvitationStatus.ACCEPTED
    await db.flush()
    await db.refresh(user, ["roles"])

    return user
