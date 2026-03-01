"""add temperature zones and room fk

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e6f
Create Date: 2026-03-01 00:30:00.000000

"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b3c4d5e6f70"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _zone_name_from_temp(value: float) -> str:
    text = f"{value:.2f}".replace("-", "neg").replace(".", "_")
    return f"MIGRATED_{text}"


def upgrade() -> None:
    # 1) Global temperature zones
    op.create_table(
        "temperature_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("zone_name", sa.String(length=128), nullable=False),
        sa.Column("min_temp", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("max_temp", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zone_name"),
    )
    op.create_index("ix_temperature_zones_zone_name", "temperature_zones", ["zone_name"], unique=True)

    # 2) Add rooms.temperature_zone_id (nullable first for migration)
    op.add_column("rooms", sa.Column("temperature_zone_id", sa.Uuid(), nullable=True))

    conn = op.get_bind()
    room_rows = conn.execute(sa.text("SELECT id, temperature_zone FROM rooms")).fetchall()

    zone_id_by_temp: dict[str, uuid.UUID] = {}

    # Default migrated zone for legacy NULL values
    default_zone_id = uuid.uuid4()
    conn.execute(
        sa.text(
            """
            INSERT INTO temperature_zones (id, zone_name, min_temp, max_temp, created_at, updated_at)
            VALUES (:id, :zone_name, :min_temp, :max_temp, now(), now())
            """
        ),
        {
            "id": default_zone_id,
            "zone_name": "MIGRATED_DEFAULT",
            "min_temp": -273.15,
            "max_temp": 200.00,
        },
    )

    for row in room_rows:
        room_id = row[0]
        legacy_temp = row[1]

        if legacy_temp is None:
            conn.execute(
                sa.text("UPDATE rooms SET temperature_zone_id = :zone_id WHERE id = :room_id"),
                {"zone_id": default_zone_id, "room_id": room_id},
            )
            continue

        temp_value = float(legacy_temp)
        key = f"{temp_value:.2f}"
        zone_id = zone_id_by_temp.get(key)
        if zone_id is None:
            zone_id = uuid.uuid4()
            zone_id_by_temp[key] = zone_id
            conn.execute(
                sa.text(
                    """
                    INSERT INTO temperature_zones (id, zone_name, min_temp, max_temp, created_at, updated_at)
                    VALUES (:id, :zone_name, :min_temp, :max_temp, now(), now())
                    """
                ),
                {
                    "id": zone_id,
                    "zone_name": _zone_name_from_temp(temp_value),
                    "min_temp": temp_value - 4.0,
                    "max_temp": temp_value + 4.0,
                },
            )

        conn.execute(
            sa.text("UPDATE rooms SET temperature_zone_id = :zone_id WHERE id = :room_id"),
            {"zone_id": zone_id, "room_id": room_id},
        )

    # 3) Enforce non-null and FK, drop old room temperature column
    op.alter_column("rooms", "temperature_zone_id", nullable=False)
    op.create_foreign_key(
        "fk_rooms_temperature_zone_id",
        "rooms",
        "temperature_zones",
        ["temperature_zone_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_rooms_temperature_zone_id", "rooms", ["temperature_zone_id"], unique=False)

    op.drop_column("rooms", "temperature_zone")

    # 4) Remove rack.temperature (now validated by room zone)
    op.drop_column("racks", "temperature")


def downgrade() -> None:
    # Restore columns
    op.add_column("racks", sa.Column("temperature", sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column("rooms", sa.Column("temperature_zone", sa.Numeric(precision=5, scale=2), nullable=True))

    # Restore room.temperature_zone from midpoint of linked zone
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE rooms AS r
            SET temperature_zone = (tz.min_temp + tz.max_temp) / 2
            FROM temperature_zones AS tz
            WHERE r.temperature_zone_id = tz.id
            """
        )
    )

    op.drop_index("ix_rooms_temperature_zone_id", table_name="rooms")
    op.drop_constraint("fk_rooms_temperature_zone_id", "rooms", type_="foreignkey")
    op.drop_column("rooms", "temperature_zone_id")

    op.drop_index("ix_temperature_zones_zone_name", table_name="temperature_zones")
    op.drop_table("temperature_zones")
