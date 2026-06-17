"""Add rate limit buckets.

Revision ID: 0006_rate_limit_buckets
Revises: 0005_password_reset_tokens
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_rate_limit_buckets"
down_revision: str | None = "0005_password_reset_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("bucket_key", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("attempts", sa.String(length=40), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rate_limit_buckets_bucket_key", "rate_limit_buckets", ["bucket_key"], unique=True)
    op.create_index("ix_rate_limit_buckets_action", "rate_limit_buckets", ["action"])
    op.create_index("ix_rate_limit_buckets_window_start", "rate_limit_buckets", ["window_start"])
    op.create_index("idx_rate_limit_action_window", "rate_limit_buckets", ["action", sa.text("window_start DESC")])


def downgrade() -> None:
    op.drop_index("idx_rate_limit_action_window", table_name="rate_limit_buckets")
    op.drop_index("ix_rate_limit_buckets_window_start", table_name="rate_limit_buckets")
    op.drop_index("ix_rate_limit_buckets_action", table_name="rate_limit_buckets")
    op.drop_index("ix_rate_limit_buckets_bucket_key", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
