"""
Authentication service.

Handles:
- Login with device-bound session enforcement
- Refresh-token rotation
- Token payload construction (includes role, session_id, device_id,
  and contextual IDs for backward-compat RBAC)
- Invitation acceptance (set password, activate account)

Concurrency rules:
- Operator: one active device at a time (same device → reuse session,
  different device → deny).
- Admin / Client: unlimited concurrent sessions.

All business logic lives here — controllers call service methods
and return the result.
"""

import uuid
from datetime import datetime, time, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.invitation import Invitation, InvitationStatus
from app.models.operator_profile import OperatorProfile
from app.models.role import Role
from app.models.session import UserSession
from app.models.user import User, UserStatus
from app.models.warehouse import Warehouse
from app.services import session_service


# ── Helpers ──────────────────────────────────────────────────────────

def _build_access_payload(user: User, *, session_id: str, device_id: str) -> dict:
    """Construct the JWT payload, keeping backward-compat keys."""
    role_names = [r.name for r in user.roles]
    payload: dict = {
        "sub": str(user.id),
        "user_id": str(user.id),           # backward compat
        "role_ids": [str(r.id) for r in user.roles],
        "role_names": role_names,
        "device_id": device_id,
        "session_id": session_id,
    }
    if user.operator_profile:
        payload["warehouse_id"] = str(user.operator_profile.warehouse_id)
    if user.client:
        payload["client_id"] = str(user.client.id)
    return payload


async def _load_user_full(user_id: uuid.UUID, db: AsyncSession) -> User:
    """Load user with roles, operator_profile, and client eagerly."""
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


# ── Login ────────────────────────────────────────────────────────────

async def authenticate_user(
    email: str,
    password: str,
    device_id: str,
    db: AsyncSession,
) -> dict:
    """
    Validate credentials, enforce device-concurrency rules, create or
    reuse a session, and return access + refresh tokens.
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

    role_names = [r.name for r in user.roles]
    now = datetime.now(timezone.utc)
    timeout_seconds = settings.SESSION_INACTIVITY_TIMEOUT_MINUTES * 60

    # ── Fetch active sessions & clean up timed-out ones ──────────────
    active_sessions = await session_service.get_active_sessions(user.id, db)

    truly_active: list[UserSession] = []
    for sess in active_sessions:
        if (now - sess.last_seen_at).total_seconds() > timeout_seconds:
            sess.is_active = False          # garbage-collect stale session
        else:
            truly_active.append(sess)

    # ── Apply concurrency rules (all roles: one device at a time) ───
    for sess in truly_active:
        if sess.device_id != device_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active session exists on another device. "
                       "Only one device is allowed per user.",
            )

    # ── Create or reuse session ──────────────────────────────────────
    existing_session: UserSession | None = None
    for sess in truly_active:
        if sess.device_id == device_id:
            existing_session = sess
            break

    session_id = existing_session.id if existing_session else uuid.uuid4()

    # Build tokens
    access_payload = _build_access_payload(
        user, session_id=str(session_id), device_id=device_id,
    )
    access_token = create_access_token(access_payload)
    refresh_token = create_refresh_token({
        "sub": str(user.id),
        "session_id": str(session_id),
        "device_id": device_id,
    })
    refresh_hash = hash_token(refresh_token)

    if existing_session:
        existing_session.refresh_token_hash = refresh_hash
        existing_session.last_seen_at = now
    else:
        new_session = UserSession(
            id=session_id,
            user_id=user.id,
            device_id=device_id,
            role=role_names[0] if role_names else "UNKNOWN",
            refresh_token_hash=refresh_hash,
        )
        db.add(new_session)

    await db.flush()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": str(user.id),
        "roles": role_names,
    }


# ── Refresh ──────────────────────────────────────────────────────────

async def refresh_access_token(refresh_token_raw: str, db: AsyncSession) -> dict:
    """
    Validate a refresh token, rotate it, and return new access + refresh
    tokens.
    """
    try:
        payload = jwt.decode(
            refresh_token_raw, settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    session_id_str = payload.get("session_id")
    user_id_str = payload.get("sub")
    if not session_id_str or not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    session = await session_service.get_active_session_by_id(
        uuid.UUID(session_id_str), db,
    )
    if session is None or str(session.user_id) != user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found or inactive",
        )

    # Verify refresh token hash
    if session.refresh_token_hash != hash_token(refresh_token_raw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token does not match — possible reuse detected",
        )

    # Load user and check status
    user = await _load_user_full(uuid.UUID(user_id_str), db)
    if user.status == UserStatus.DISABLED:
        await session_service.deactivate_session(session.id, db)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    role_names = [r.name for r in user.roles]

    # Build rotated tokens
    new_access_payload = _build_access_payload(
        user, session_id=str(session.id), device_id=session.device_id,
    )
    new_access_token = create_access_token(new_access_payload)
    new_refresh_token = create_refresh_token({
        "sub": str(user.id),
        "session_id": str(session.id),
        "device_id": session.device_id,
    })

    # Rotate refresh token hash
    session.refresh_token_hash = hash_token(new_refresh_token)
    session.last_seen_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "user_id": str(user.id),
        "roles": role_names,
    }


async def accept_invitation(
    token: str,
    password: str,
    full_name: str,
    warehouse_id: uuid.UUID | None,
    shift_start: time | None,
    shift_end: time | None,
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

    # Create a new operator profile if the role is OPERATOR
    if role.name == "OPERATOR":
        if warehouse_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Warehouse ID is required for OPERATOR role",
            )
        operator_profile = OperatorProfile(
            user_id=user.id,
            warehouse_id=warehouse_id,
            shift_start=shift_start,
            shift_end=shift_end,
        )
        db.add(operator_profile)

    invite.status = InvitationStatus.ACCEPTED
    await db.flush()
    await db.refresh(user, ["roles"])

    return user

async def get_invitation_by_token(token: str, db: AsyncSession) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.token == token)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_all_warehouses(db: AsyncSession) -> list[Warehouse]:
    stmt = select(Warehouse)
    result = await db.execute(stmt)
    return result.scalars().all()
