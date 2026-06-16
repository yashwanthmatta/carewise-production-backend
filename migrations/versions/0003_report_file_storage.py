"""Add report file storage metadata.

Revision ID: 0003_report_file_storage
Revises: 0002_product_systems
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003_report_file_storage"
down_revision: str | None = "0002_product_systems"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("report_uploads", sa.Column("storage_key", sa.Text(), nullable=False, server_default=""))
    op.add_column("report_uploads", sa.Column("file_size_bytes", sa.String(length=40), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("report_uploads", "file_size_bytes")
    op.drop_column("report_uploads", "storage_key")
