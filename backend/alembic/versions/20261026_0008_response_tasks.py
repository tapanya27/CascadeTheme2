"""Create response_tasks for Action Center workflow.

Revision ID: 20261026_0008
Revises: 20261026_0007
Create Date: 2026-10-26

Safe additive migration — does not drop tables or delete rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261026_0008"
down_revision: Union[str, None] = "20261026_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "response_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city_id", sa.String(length=64), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("why_recommended", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="officer"),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("next_step", sa.Text(), nullable=True),
        sa.Column(
            "notes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "audit",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_response_tasks_city_id", "response_tasks", ["city_id"])
    op.create_index("ix_response_tasks_zone_id", "response_tasks", ["zone_id"])
    op.create_index("ix_response_tasks_status", "response_tasks", ["status"])
    op.create_index("ix_response_tasks_created_at", "response_tasks", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_response_tasks_created_at", table_name="response_tasks")
    op.drop_index("ix_response_tasks_status", table_name="response_tasks")
    op.drop_index("ix_response_tasks_zone_id", table_name="response_tasks")
    op.drop_index("ix_response_tasks_city_id", table_name="response_tasks")
    op.drop_table("response_tasks")
