"""Dual-rank assessment columns + community_reports

Revision ID: 20261025_0004
Revises: 20260325_0003
Create Date: 2026-10-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261025_0004"
down_revision: Union[str, None] = "20260325_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vulnerability_assessments",
        sa.Column("hazard_only_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "vulnerability_assessments",
        sa.Column("hazard_only_rank", sa.Integer(), nullable=True),
    )
    op.add_column(
        "vulnerability_assessments",
        sa.Column("multifactor_rank", sa.Integer(), nullable=True),
    )
    op.add_column(
        "vulnerability_assessments",
        sa.Column("rank_uplift", sa.Integer(), nullable=True),
    )

    op.create_table(
        "community_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city_id", sa.String(64), nullable=True),
        sa.Column("text_redacted", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("near_duplicate_key", sa.String(64), nullable=True),
        sa.Column("disaster_related", sa.Boolean(), nullable=True),
        sa.Column("disaster_related_proba", sa.Float(), nullable=True),
        sa.Column(
            "labels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "label_probas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("needs_human_review", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("location_precision", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column(
            "location",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("observation_kind", sa.String(32), nullable=False, server_default="unverified"),
        sa.Column(
            "source_reliability",
            sa.String(64),
            nullable=False,
            server_default="unverified_community",
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_community_reports_city_id", "community_reports", ["city_id"])
    op.create_index("ix_community_reports_text_hash", "community_reports", ["text_hash"])
    op.create_index(
        "ix_community_reports_near_duplicate_key",
        "community_reports",
        ["near_duplicate_key"],
    )
    op.create_index("ix_community_reports_observed_at", "community_reports", ["observed_at"])
    op.create_index("ix_community_reports_created_at", "community_reports", ["created_at"])


def downgrade() -> None:
    op.drop_table("community_reports")
    op.drop_column("vulnerability_assessments", "rank_uplift")
    op.drop_column("vulnerability_assessments", "multifactor_rank")
    op.drop_column("vulnerability_assessments", "hazard_only_rank")
    op.drop_column("vulnerability_assessments", "hazard_only_score")
