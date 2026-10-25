"""Add verification_status to community_reports.

Revision ID: 20261025_0006
Revises: 20261025_0005
Create Date: 2026-10-25

Safe additive migration — does not drop tables or delete rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0006"
down_revision: Union[str, None] = "20261025_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "community_reports",
        sa.Column("verification_status", sa.String(length=32), nullable=True),
    )
    op.execute(
        "UPDATE community_reports SET verification_status = 'unverified' "
        "WHERE verification_status IS NULL"
    )
    op.execute(
        "UPDATE community_reports SET verification_status = 'verified' "
        "WHERE reviewed = true"
    )
    op.alter_column("community_reports", "verification_status", nullable=False)
    op.create_index(
        "ix_community_reports_verification_status",
        "community_reports",
        ["verification_status"],
    )

    op.add_column(
        "community_reports",
        sa.Column("category", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE community_reports
        SET category = CASE
            WHEN jsonb_typeof(labels) = 'array'
                 AND jsonb_array_length(labels) > 0
            THEN labels->>0
            WHEN disaster_related IS TRUE THEN 'unclassified'
            WHEN disaster_related IS FALSE THEN 'not_disaster_related'
            ELSE 'unclassified'
        END
        WHERE category IS NULL
        """
    )
    op.alter_column("community_reports", "category", nullable=False)

    # city_id is required for isolation going forward
    op.execute(
        "UPDATE community_reports SET city_id = 'nagpur' WHERE city_id IS NULL"
    )
    op.alter_column("community_reports", "city_id", nullable=False)


def downgrade() -> None:
    op.alter_column("community_reports", "city_id", nullable=True)
    op.drop_column("community_reports", "category")
    op.drop_index(
        "ix_community_reports_verification_status",
        table_name="community_reports",
    )
    op.drop_column("community_reports", "verification_status")
