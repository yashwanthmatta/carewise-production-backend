"""Add data deletion request records.

Revision ID: 0004_data_deletion_requests
Revises: 0003_report_file_storage
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004_data_deletion_requests"
down_revision: str | None = "0003_report_file_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_deletion_requests",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_data_deletion_requests_user_id", "data_deletion_requests", ["user_id"])
    op.create_index("ix_data_deletion_requests_email", "data_deletion_requests", ["email"])
    op.create_index("ix_data_deletion_requests_status", "data_deletion_requests", ["status"])
    op.create_index("idx_deletion_requests_user_created", "data_deletion_requests", ["user_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_deletion_requests_user_created", table_name="data_deletion_requests")
    op.drop_table("data_deletion_requests")
