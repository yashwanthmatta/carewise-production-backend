"""Add email verification records.

Revision ID: 0008_email_verification
Revises: 0007_refresh_tokens
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008_email_verification"
down_revision: str | None = "0007_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified", sa.String(length=10), nullable=False, server_default="false"))
    op.create_index("ix_users_email_verified", "users", ["email_verified"])
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])
    op.create_index("ix_email_verification_tokens_token_hash", "email_verification_tokens", ["token_hash"], unique=True)
    op.create_index("ix_email_verification_tokens_status", "email_verification_tokens", ["status"])
    op.create_index("ix_email_verification_tokens_expires_at", "email_verification_tokens", ["expires_at"])
    op.create_index(
        "idx_email_verification_user_created",
        "email_verification_tokens",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_email_verification_user_created", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_expires_at", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_status", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_token_hash", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_index("ix_users_email_verified", table_name="users")
    op.drop_column("users", "email_verified")
