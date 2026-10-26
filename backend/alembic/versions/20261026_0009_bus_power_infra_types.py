"""Add bus_route and power_asset infrastructure types.

Revision ID: 20261026_0009
Revises: 20261026_0008
Create Date: 2026-10-26
"""

from __future__ import annotations

from alembic import op

revision = "20261026_0009"
down_revision = "20261026_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL ENUM — ADD VALUE cannot run inside a transaction block on some versions;
    # use IF NOT EXISTS where available (PG 9.1+ for ADD VALUE, IF NOT EXISTS since PG 9.3+).
    op.execute("ALTER TYPE infrastructure_type ADD VALUE IF NOT EXISTS 'bus_route'")
    op.execute("ALTER TYPE infrastructure_type ADD VALUE IF NOT EXISTS 'power_asset'")


def downgrade() -> None:
    # Enum value removal is not supported safely in PostgreSQL without recreating the type.
    pass
