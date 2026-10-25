"""Add city_id isolation columns to core geospatial tables.

Revision ID: 20261025_0005
Revises: 20261025_0004
Create Date: 2026-10-25

Does not drop tables or delete rows. Existing rows are backfilled to city_id='nagpur'.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0005"
down_revision: Union[str, None] = "20261025_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # data_sources
    op.add_column(
        "data_sources",
        sa.Column("city_id", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE data_sources SET city_id = 'nagpur' WHERE city_id IS NULL")
    op.alter_column("data_sources", "city_id", nullable=False)
    op.create_index("ix_data_sources_city_id", "data_sources", ["city_id"])
    op.drop_constraint("data_sources_name_key", "data_sources", type_="unique")
    op.create_unique_constraint(
        "uq_data_sources_city_name", "data_sources", ["city_id", "name"]
    )

    # zones — replace global code uniqueness with per-city
    op.add_column(
        "zones",
        sa.Column("city_id", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE zones SET city_id = 'nagpur' WHERE city_id IS NULL")
    op.alter_column("zones", "city_id", nullable=False)
    op.create_index("ix_zones_city_id", "zones", ["city_id"])
    op.drop_constraint("uq_zones_code", "zones", type_="unique")
    op.create_unique_constraint("uq_zones_city_code", "zones", ["city_id", "code"])

    # infrastructure
    op.add_column(
        "infrastructure",
        sa.Column("city_id", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE infrastructure SET city_id = 'nagpur' WHERE city_id IS NULL")
    op.alter_column("infrastructure", "city_id", nullable=False)
    op.create_index("ix_infrastructure_city_id", "infrastructure", ["city_id"])

    # hazard_observations
    op.add_column(
        "hazard_observations",
        sa.Column("city_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE hazard_observations SET city_id = 'nagpur' WHERE city_id IS NULL"
    )
    op.alter_column("hazard_observations", "city_id", nullable=False)
    op.create_index(
        "ix_hazard_observations_city_id", "hazard_observations", ["city_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_hazard_observations_city_id", table_name="hazard_observations")
    op.drop_column("hazard_observations", "city_id")

    op.drop_index("ix_infrastructure_city_id", table_name="infrastructure")
    op.drop_column("infrastructure", "city_id")

    op.drop_constraint("uq_zones_city_code", "zones", type_="unique")
    op.drop_index("ix_zones_city_id", table_name="zones")
    op.drop_column("zones", "city_id")
    op.create_unique_constraint("uq_zones_code", "zones", ["code"])

    op.drop_constraint("uq_data_sources_city_name", "data_sources", type_="unique")
    op.drop_index("ix_data_sources_city_id", table_name="data_sources")
    op.drop_column("data_sources", "city_id")
    op.create_unique_constraint("data_sources_name_key", "data_sources", ["name"])
