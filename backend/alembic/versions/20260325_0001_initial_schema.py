"""Initial PostGIS schema: data_sources, zones, infrastructure, hazard_observations

Revision ID: 20260325_0001
Revises:
Create Date: 2026-03-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "20260325_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    data_source_kind = postgresql.ENUM(
        "authentic",
        "synthetic",
        "openstreetmap",
        "csv_import",
        "geojson_import",
        "other",
        name="data_source_kind",
        create_type=False,
    )
    infrastructure_type = postgresql.ENUM(
        "hospital",
        "clinic",
        "emergency_facility",
        "road",
        "other",
        name="infrastructure_type",
        create_type=False,
    )
    hazard_type = postgresql.ENUM(
        "flood",
        "waterlogging",
        "other",
        name="hazard_type",
        create_type=False,
    )
    severity_level = postgresql.ENUM(
        "low",
        "moderate",
        "high",
        "severe",
        "unknown",
        name="severity_level",
        create_type=False,
    )

    data_source_kind.create(op.get_bind(), checkfirst=True)
    infrastructure_type.create(op.get_bind(), checkfirst=True)
    hazard_type.create(op.get_bind(), checkfirst=True)
    severity_level.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "kind",
            data_source_kind,
            nullable=False,
        ),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(255), nullable=True),
        sa.Column("retrieval_url", sa.Text(), nullable=True),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "boundary",
            Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("code", name="uq_zones_code"),
    )
    op.create_index("ix_zones_data_source_id", "zones", ["data_source_id"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_zones_boundary ON zones USING GIST (boundary)"
    )

    op.create_table(
        "infrastructure",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("infrastructure_type", infrastructure_type, nullable=False),
        sa.Column(
            "geometry",
            Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "external_id", "data_source_id", name="uq_infra_external_source"
        ),
    )
    op.create_index(
        "ix_infrastructure_infrastructure_type",
        "infrastructure",
        ["infrastructure_type"],
    )
    op.create_index("ix_infrastructure_zone_id", "infrastructure", ["zone_id"])
    op.create_index(
        "ix_infrastructure_data_source_id", "infrastructure", ["data_source_id"]
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_infrastructure_geometry "
        "ON infrastructure USING GIST (geometry)"
    )

    op.create_table(
        "hazard_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("hazard_type", hazard_type, nullable=False),
        sa.Column("severity", severity_level, nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity_score", sa.Float(), nullable=True),
        sa.Column(
            "geometry",
            Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_hazard_observations_hazard_type", "hazard_observations", ["hazard_type"]
    )
    op.create_index(
        "ix_hazard_observations_observed_on", "hazard_observations", ["observed_on"]
    )
    op.create_index("ix_hazard_observations_zone_id", "hazard_observations", ["zone_id"])
    op.create_index(
        "ix_hazard_observations_data_source_id",
        "hazard_observations",
        ["data_source_id"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hazard_observations_geometry "
        "ON hazard_observations USING GIST (geometry)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_hazard_observations_geometry")
    op.drop_table("hazard_observations")
    op.execute("DROP INDEX IF EXISTS idx_infrastructure_geometry")
    op.drop_table("infrastructure")
    op.execute("DROP INDEX IF EXISTS idx_zones_boundary")
    op.drop_table("zones")
    op.drop_table("data_sources")

    op.execute("DROP TYPE IF EXISTS severity_level")
    op.execute("DROP TYPE IF EXISTS hazard_type")
    op.execute("DROP TYPE IF EXISTS infrastructure_type")
    op.execute("DROP TYPE IF EXISTS data_source_kind")
