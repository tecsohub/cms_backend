"""
Pydantic schemas for request / response serialization.

Kept in a single file for now — split per-domain when it grows.
Schemas are deliberately decoupled from SQLAlchemy models so the
API surface can evolve independently of the DB layer.
"""

import uuid
from datetime import datetime, time
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


# ── Auth ─────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    roles: list[str]


class AcceptInvitationRequest(BaseModel):
    warehouse_id: str
    token: str
    password: str = Field(min_length=8)
    full_name: str


# ── User ─────────────────────────────────────────────────────────────
class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None = None
    address: str | None = None
    status: str
    roles: list[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Invitation ───────────────────────────────────────────────────────
class CreateInvitationRequest(BaseModel):
    email: str
    role_assigned: str


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role_assigned: str
    token: str
    status: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Warehouse ────────────────────────────────────────────────────────
class CreateWarehouseRequest(BaseModel):
    name: str
    address: str
    capacity: int | None = None


class UpdateWarehouseRequest(BaseModel):
    name: str | None = None
    address: str | None = None
    capacity: int | None = None


class WarehouseOut(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    capacity: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Operator Profile ────────────────────────────────────────────────
class OperatorProfileOut(BaseModel):
    user_id: uuid.UUID
    warehouse_id: uuid.UUID
    shift_start: time | None = None
    shift_end: time | None = None

    model_config = {"from_attributes": True}


# ── Client ───────────────────────────────────────────────────────────
class ClientOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    company_name: str
    billing_address: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Generic ──────────────────────────────────────────────────────────
class MessageResponse(BaseModel):
    detail: str
