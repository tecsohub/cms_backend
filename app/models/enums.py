"""
Shared ENUM types for inventory ledger and audit log.

These are defined separately so they can be imported by models,
services, and migrations without circular dependencies.
"""

import enum


class MovementType(str, enum.Enum):
    """Types of inventory quantity mutations tracked in the ledger."""

    INWARD = "INWARD"
    ALLOCATION = "ALLOCATION"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
    OUTWARD = "OUTWARD"
    ADJUSTMENT = "ADJUSTMENT"
    WASTE = "WASTE"


class AuditAction(str, enum.Enum):
    """Entity-level actions tracked in the system audit log."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    DISABLE = "DISABLE"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ALLOCATE = "ALLOCATE"
    CLOSE = "CLOSE"
    PASSWORD_RESET = "PASSWORD_RESET"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
