"""Add doctor share links: read-only, expiring summaries a family can give a doctor.

Revision ID: 0012_doctor_shares
Revises: 0011_subscription_customer
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0012_doctor_shares"
down_revision: str | None = "0011_subscription_customer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "doctor_shares",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_label", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_snapshot", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_doctor_shares_user_id", "doctor_shares", ["user_id"])
    op.create_index("ix_doctor_shares_token_hash", "doctor_shares", ["token_hash"], unique=True)
    op.create_index("ix_doctor_shares_expires_at", "doctor_shares", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_doctor_shares_expires_at", table_name="doctor_shares")
    op.drop_index("ix_doctor_shares_token_hash", table_name="doctor_shares")
    op.drop_index("ix_doctor_shares_user_id", table_name="doctor_shares")
    op.drop_table("doctor_shares")
