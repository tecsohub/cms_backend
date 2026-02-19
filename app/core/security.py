"""
Password hashing & JWT helpers.

- Passwords are hashed with bcrypt directly (passlib is unmaintained
  and broken with bcrypt>=4.1).
- JWTs carry user_id, role, device_id, session_id, and contextual IDs.
- Token verification validates against the server-side session
  registry on EVERY request (hybrid stateful JWT).
- Refresh tokens support rotation with SHA-256 hash storage.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.session import UserSession

# ── Password hashing ────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Token hashing (for refresh tokens) ──────────────────────────────


def hash_token(token: str) -> str:
    """SHA-256 hash — suitable for high-entropy tokens like JWTs."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── JWT ──────────────────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a long-lived refresh token with rotation support."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode & validate a JWT.  Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Per-request session validation ──────────────────────────────────


async def get_current_user_token(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    FastAPI dependency — decodes the JWT **and** validates the session
    against the server-side session registry.

    Checks performed on every protected request:
      1. JWT signature & expiry.
      2. Session exists, belongs to user, and is active.
      3. Device ID in JWT matches session record.
      4. Session has not exceeded the inactivity timeout.

    On success, updates ``last_seen_at`` (committed with the request
    transaction).
    """
    payload = decode_access_token(token)

    session_id = payload.get("session_id")
    user_id = payload.get("sub") or payload.get("user_id")
    device_id = payload.get("device_id")

    if not all([session_id, user_id, device_id]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload — missing session fields",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Query the session registry
    stmt = select(UserSession).where(
        UserSession.id == uuid.UUID(session_id),
        UserSession.user_id == uuid.UUID(str(user_id)),
        UserSession.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if session.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device mismatch — session invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Inactivity timeout check
    now = datetime.now(timezone.utc)
    elapsed_seconds = (now - session.last_seen_at).total_seconds()
    if elapsed_seconds > settings.SESSION_INACTIVITY_TIMEOUT_MINUTES * 60:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session timed out due to inactivity",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last_seen_at (best-effort — committed with the request)
    session.last_seen_at = now

    return payload
