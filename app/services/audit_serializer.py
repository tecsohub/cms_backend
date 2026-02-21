"""
Audit serialization helper.

Converts a SQLAlchemy model instance into a plain dict suitable for
storing in the audit_log JSONB columns (old_data / new_data).

Rules:
- Include scalar (column) attributes only.
- Convert UUID → str, Decimal → str, datetime → ISO 8601.
- Exclude relationships, large blobs, and secrets.
- Output must be deterministic and JSON-serialisable.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect

# Column names that must NEVER appear in audit snapshots.
_EXCLUDED_COLUMNS: frozenset[str] = frozenset(
    {
        "password_hash",
        "refresh_token_hash",
        "token",  # invitation secret
    }
)


def _serialise_value(value: Any) -> Any:
    """Convert a single Python value to a JSON-safe representation."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    # str / int / float / bool — already JSON-safe
    return value


# We need to import enum.Enum properly
from enum import Enum  # noqa: E402


def to_audit_dict(entity: Any) -> dict[str, Any]:
    """
    Serialise a SQLAlchemy ORM instance to a plain dict for audit storage.

    Only mapper-level column attributes are included; relationships,
    hybrid properties, and excluded secrets are omitted.
    """
    mapper = sa_inspect(type(entity))
    result: dict[str, Any] = {}

    for col_attr in mapper.column_attrs:
        key = col_attr.key
        if key in _EXCLUDED_COLUMNS:
            continue
        value = getattr(entity, key, None)
        result[key] = _serialise_value(value)

    return result
