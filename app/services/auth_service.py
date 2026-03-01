"""
Authentication service.

Handles:
- Login with device-bound session enforcement
- Refresh-token rotation
- Token payload construction (includes role, session_id, device_id,
  and contextual IDs for backward-compat RBAC)
- Invitation acceptance (set password, activate account)
- Forgot-password (OTP email flow)
- Change-password (authenticated)

Concurrency rules:
- Operator: one active device at a time (same device → reuse session,
  different device → deny).
- Admin / Client: unlimited concurrent sessions.

All business logic lives here — controllers call service methods
and return the result.
"""

import hashlib
import random
import uuid
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import func, select
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
from app.models.password_reset_otp import PasswordResetOTP
from app.models.role import Role
from app.models.session import UserSession
from app.models.user import User, UserStatus
from app.models.warehouse import Warehouse
from app.models.enums import AuditAction
from app.services import audit_service, session_service
from app.services.audit_serializer import to_audit_dict
from app.services import product_service


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

        await audit_service.log(
            db,
            entity_type="User",
            entity_id=user.id,
            action="CREATE",
            performed_by=user.id,
            old_data=None,
            new_data=to_audit_dict(user),
        )
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

    # Create a client profile if the role is CLIENT
    if role.name == "CLIENT":
        from app.models.client import Client

        existing_client = (
            await db.execute(select(Client).where(Client.user_id == user.id))
        ).scalar_one_or_none()

        if existing_client is None:
            client = Client(
                id=uuid.uuid4(),
                user_id=user.id,
                company_name=full_name,  # default to user's name
                created_by_admin_id=invite.invited_by,
            )
            db.add(client)
            await db.flush()

            # Back-fill client_id on any products awaiting this email
            await product_service.backfill_client_on_products(
                client_id=client.id,
                client_email=invite.email,
                performed_by=user.id,
                db=db,
            )

    invite.status = InvitationStatus.ACCEPTED
    await db.flush()
    await db.refresh(user, ["roles"])

    # Audit: role assignment
    await audit_service.log(
        db,
        entity_type="UserRole",
        entity_id=user.id,
        action="UPDATE",
        performed_by=user.id,
        old_data=None,
        new_data={"user_id": str(user.id), "role": role.name},
        reason=f"Role '{role.name}' assigned via invitation acceptance",
    )

    return user

async def get_invitation_by_token(token: str, db: AsyncSession) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.token == token)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_all_warehouses(db: AsyncSession) -> list[Warehouse]:
    stmt = select(Warehouse)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Forgot Password (OTP) ───────────────────────────────────────────


def _generate_otp(length: int = 6) -> str:
    """Return a cryptographically-acceptable numeric OTP string."""
    return "".join(str(random.SystemRandom().randint(0, 9)) for _ in range(length))


def _hash_otp(otp: str) -> str:
    """SHA-256 hash the OTP before persisting."""
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


async def request_password_reset(email: str, db: AsyncSession) -> dict:
    """
    Generate a 6-digit OTP and email it.

    Rules:
    - Always returns a generic success message (prevents user enumeration).
    - Rate limited to OTP_MAX_DAILY_REQUESTS per email per UTC day.
    - Only active users receive the OTP; silent no-op otherwise.
    """
    from app.services.email_service import send_password_reset_otp_email

    # Always return generic message regardless of outcome
    generic_response = {
        "detail": "If the email is registered, a password reset code has been sent."
    }

    # Look up user
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or user.status != UserStatus.ACTIVE:
        return generic_response

    # ── Rate limit: max N requests per UTC day ───────────────────────
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    count_stmt = (
        select(func.count())
        .select_from(PasswordResetOTP)
        .where(
            PasswordResetOTP.email == email,
            PasswordResetOTP.created_at >= today_start,
        )
    )
    daily_count = (await db.execute(count_stmt)).scalar() or 0

    if daily_count >= settings.OTP_MAX_DAILY_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many password reset requests today. Please try again tomorrow.",
        )

    # ── Invalidate any existing unused OTPs for this user ────────────
    prev_stmt = (
        select(PasswordResetOTP)
        .where(
            PasswordResetOTP.user_id == user.id,
            PasswordResetOTP.is_used == False,  # noqa: E712
        )
    )
    prev_result = await db.execute(prev_stmt)
    for old_otp in prev_result.scalars():
        old_otp.is_used = True

    # ── Create new OTP ───────────────────────────────────────────────
    otp_plain = _generate_otp()
    otp_record = PasswordResetOTP(
        id=uuid.uuid4(),
        user_id=user.id,
        email=email,
        otp_hash=_hash_otp(otp_plain),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(otp_record)
    await db.flush()

    # ── Send email ───────────────────────────────────────────────────
    await send_password_reset_otp_email(email, otp_plain)

    return generic_response


async def reset_password_with_otp(
    email: str,
    otp: str,
    new_password: str,
    db: AsyncSession,
) -> dict:
    """
    Validate the OTP and set the new password.

    After success:
    - OTP is marked used.
    - All active sessions are revoked (forces re-login everywhere).
    - Audit log entry is created.
    """
    # Find the latest unused, non-expired OTP for this email
    stmt = (
        select(PasswordResetOTP)
        .where(
            PasswordResetOTP.email == email,
            PasswordResetOTP.is_used == False,  # noqa: E712
            PasswordResetOTP.expires_at > datetime.now(timezone.utc),
        )
        .order_by(PasswordResetOTP.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    otp_record = result.scalar_one_or_none()

    if otp_record is None or otp_record.otp_hash != _hash_otp(otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP.",
        )

    # ── Load user ────────────────────────────────────────────────────
    user_stmt = select(User).where(User.id == otp_record.user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP.",
        )

    # ── Update password ──────────────────────────────────────────────
    user.password_hash = hash_password(new_password)
    otp_record.is_used = True

    # ── Revoke all sessions ──────────────────────────────────────────
    revoked = await session_service.deactivate_all_user_sessions(user.id, db)

    # ── Audit ────────────────────────────────────────────────────────
    await audit_service.log(
        db,
        entity_type="User",
        entity_id=user.id,
        action=AuditAction.PASSWORD_RESET,
        performed_by=user.id,
        old_data=None,
        new_data={"sessions_revoked": revoked},
        reason="Password reset via OTP",
    )

    await db.flush()
    return {"detail": "Password has been reset successfully. Please log in again."}


async def change_password(
    user_id: uuid.UUID,
    current_password: str,
    new_password: str,
    db: AsyncSession,
) -> dict:
    """
    Authenticated password change.

    - Validates the current password.
    - Sets the new password.
    - Revokes all active sessions (forces re-login everywhere).
    - Audit-logged.
    """
    user_stmt = select(User).where(User.id == user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if not verify_password(current_password, user.password_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    if current_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password.",
        )

    # ── Update password ──────────────────────────────────────────────
    user.password_hash = hash_password(new_password)

    # ── Revoke all sessions ──────────────────────────────────────────
    revoked = await session_service.deactivate_all_user_sessions(user.id, db)

    # ── Audit ────────────────────────────────────────────────────────
    await audit_service.log(
        db,
        entity_type="User",
        entity_id=user.id,
        action=AuditAction.PASSWORD_CHANGE,
        performed_by=user.id,
        old_data=None,
        new_data={"sessions_revoked": revoked},
        reason="User changed password",
    )

    await db.flush()
    return {"detail": "Password changed successfully. Please log in again."}
