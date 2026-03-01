"""add password actions to audit_action enum

Revision ID: 9c1d2e3f4a5b
Revises: f6a7b8c9d0e1
Create Date: 2026-03-01 00:30:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c1d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing password-related values to audit_action enum in all schemas."""
    op.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT n.nspname AS schema_name
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'audit_action'
            LOOP
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_enum e
                    JOIN pg_type t2 ON t2.oid = e.enumtypid
                    JOIN pg_namespace n2 ON n2.oid = t2.typnamespace
                    WHERE t2.typname = 'audit_action'
                      AND n2.nspname = r.schema_name
                      AND e.enumlabel = 'PASSWORD_RESET'
                ) THEN
                    EXECUTE format(
                        'ALTER TYPE %I.audit_action ADD VALUE ''PASSWORD_RESET''',
                        r.schema_name
                    );
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_enum e
                    JOIN pg_type t2 ON t2.oid = e.enumtypid
                    JOIN pg_namespace n2 ON n2.oid = t2.typnamespace
                    WHERE t2.typname = 'audit_action'
                      AND n2.nspname = r.schema_name
                      AND e.enumlabel = 'PASSWORD_CHANGE'
                ) THEN
                    EXECUTE format(
                        'ALTER TYPE %I.audit_action ADD VALUE ''PASSWORD_CHANGE''',
                        r.schema_name
                    );
                END IF;
            END LOOP;
        END
        $$;
        """
    )


def downgrade() -> None:
    """No-op: PostgreSQL ENUM values cannot be dropped safely in-place."""
    pass
