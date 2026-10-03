"""Add product signals: usage counters, feedback and early-access sign-ups.

Revision ID: 0010_product_signals
Revises: 0009_lab_trends
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0010_product_signals"
down_revision: str | None = "0009_lab_trends"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_counters",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("day", "name", "source", name="uq_usage_counters_day_name_source"),
    )
    op.create_index("ix_usage_counters_day", "usage_counters", ["day"])
    op.create_index("ix_usage_counters_name", "usage_counters", ["name"])
    op.create_table(
        "product_feedback",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("helpful", sa.String(length=10), nullable=False),
        sa.Column("encrypted_comment", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_feedback_helpful", "product_feedback", ["helpful"])
    op.create_table(
        "early_access_signups",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_email", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("encrypted_note", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_early_access_signups_email_hash", "early_access_signups", ["email_hash"], unique=True)
    op.create_index("ix_early_access_signups_role", "early_access_signups", ["role"])


def downgrade() -> None:
    op.drop_index("ix_early_access_signups_role", table_name="early_access_signups")
    op.drop_index("ix_early_access_signups_email_hash", table_name="early_access_signups")
    op.drop_table("early_access_signups")
    op.drop_index("ix_product_feedback_helpful", table_name="product_feedback")
    op.drop_table("product_feedback")
    op.drop_index("ix_usage_counters_name", table_name="usage_counters")
    op.drop_index("ix_usage_counters_day", table_name="usage_counters")
    op.drop_table("usage_counters")
