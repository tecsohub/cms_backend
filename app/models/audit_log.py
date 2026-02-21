"""
System Audit Log model — governance & entity change tracking.

This table is **append-only** and **immutable**.
It records entity-level changes across the entire system for
compliance, dispute resolution, and governance traceability.

Rules:
- No UPDATE operations allowed.
- No DELETE operations allowed.
- No cascading delete from parent entities.
- old_data / new_data store serialized JSONB snapshots (scalars only).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AuditAction

# Use generic JSON with a PostgreSQL JSONB variant so the model works
# on both PostgreSQL (production) and SQLite (tests).
_JsonType = JSON().with_variant(JSONB, "postgresql")


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_log"

    # ── Entity reference ─────────────────────────────────────────────
    entity_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
        index=True,
    )

    # ── Action performed ─────────────────────────────────────────────
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action", create_constraint=True),
        nullable=False,
    )

    # ── Who performed the action ─────────────────────────────────────
    performed_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Before / after snapshots ─────────────────────────────────────
    old_data: Mapped[dict | None] = mapped_column(_JsonType, nullable=True)
    new_data: Mapped[dict | None] = mapped_column(_JsonType, nullable=True)

    # ── Optional human reason ────────────────────────────────────────
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timestamp ────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── Composite indexes ────────────────────────────────────────────
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog {self.action.value} "
            f"{self.entity_type}:{self.entity_id}>"
        )
