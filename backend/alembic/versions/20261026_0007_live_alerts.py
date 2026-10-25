"""Create live_alerts table for notification + map workflow.

Revision ID: 20261026_0007
Revises: 20261025_0006
Create Date: 2026-10-26

Safe additive migration — does not drop tables or delete rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261026_0007"
down_revision: Union[str, None] = "20261025_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "live_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city_id", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("source_event_id", sa.String(length=256), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("has_reliable_coords", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("zone_code", sa.String(length=64), nullable=True),
        sa.Column("area_label", sa.String(length=256), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "authenticity",
            sa.String(length=32),
            nullable=False,
            server_default="demo",
        ),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.UniqueConstraint(
            "source_name", "source_event_id", name="uq_live_alerts_source_event"
        ),
    )
    op.create_index("ix_live_alerts_city_id", "live_alerts", ["city_id"])
    op.create_index("ix_live_alerts_source_name", "live_alerts", ["source_name"])
    op.create_index("ix_live_alerts_alert_type", "live_alerts", ["alert_type"])
    op.create_index("ix_live_alerts_zone_id", "live_alerts", ["zone_id"])
    op.create_index("ix_live_alerts_ingested_at", "live_alerts", ["ingested_at"])


def downgrade() -> None:
    op.drop_index("ix_live_alerts_ingested_at", table_name="live_alerts")
    op.drop_index("ix_live_alerts_zone_id", table_name="live_alerts")
    op.drop_index("ix_live_alerts_alert_type", table_name="live_alerts")
    op.drop_index("ix_live_alerts_source_name", table_name="live_alerts")
    op.drop_index("ix_live_alerts_city_id", table_name="live_alerts")
    op.drop_table("live_alerts")
