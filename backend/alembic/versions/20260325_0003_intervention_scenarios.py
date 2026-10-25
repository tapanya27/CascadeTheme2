"""Add intervention_scenarios table

Revision ID: 20260325_0003
Revises: 20260325_0002
Create Date: 2026-03-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260325_0003"
down_revision: Union[str, None] = "20260325_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    intervention_type = postgresql.ENUM(
        "place_temporary_resource",
        "accessibility_improvement",
        "alternative_emergency_route",
        "compare_resource_placements",
        name="intervention_type",
        create_type=False,
    )
    intervention_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "intervention_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("intervention_type", intervention_type, nullable=False),
        sa.Column("scoring_version", sa.String(64), nullable=False),
        sa.Column(
            "assumptions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "baseline",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "limitations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_intervention_scenarios_zone_id", "intervention_scenarios", ["zone_id"]
    )
    op.create_index(
        "ix_intervention_scenarios_intervention_type",
        "intervention_scenarios",
        ["intervention_type"],
    )
    op.create_index(
        "ix_intervention_scenarios_created_at",
        "intervention_scenarios",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("intervention_scenarios")
    op.execute("DROP TYPE IF EXISTS intervention_type")
