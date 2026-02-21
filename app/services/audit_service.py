"""
Audit service — writes to the system audit_log table.

Public API:
    await audit_service.log(db, entity_type, entity_id, action,
                            performed_by, old_data, new_data, reason)

Transactional contract:
- Must NOT commit.
- Must NOT start its own transaction.
- Relies on the outer transaction scope.
- If insertion fails, the exception propagates and the outer
  transaction rolls back (business mutation + audit together).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction


async def log(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    action: AuditAction | str,
    performed_by: uuid.UUID,
    old_data: dict | None = None,
    new_data: dict | None = None,
    reason: str | None = None,
) -> AuditLog:
    """
    Insert one row into the audit_log table.

    Parameters
    ----------
    db : AsyncSession
        The *same* session used by the calling service — no new
        transaction is created.
    entity_type : str
        Logical name of the entity (e.g. "User", "Warehouse").
    entity_id : UUID
        Primary key of the affected entity.
    action : AuditAction | str
        The mutation that occurred.
    performed_by : UUID
        The user who performed the action.
    old_data : dict | None
        JSONB snapshot of the entity **before** the change.
    new_data : dict | None
        JSONB snapshot of the entity **after** the change.
    reason : str | None
        Optional human-readable justification.

    Returns
    -------
    AuditLog
        The newly created (but not yet committed) audit row.

    Raises
    ------
    Exception
        Any DB error propagates to the caller so the outer transaction
        can roll back.
    """
    # Normalise string action to enum if needed
    if isinstance(action, str):
        action = AuditAction(action)

    entry = AuditLog(
        id=uuid.uuid4(),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        performed_by=performed_by,
        old_data=old_data,
        new_data=new_data,
        reason=reason,
    )
    db.add(entry)
    await db.flush()
    return entry
