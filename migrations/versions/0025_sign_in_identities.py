"""Sign-in identities (Google, Apple, Microsoft) and short-lived sign-in flow values.

Additive only: two new tables. Existing users, passwords and records are not touched.

Revision ID: 0025_sign_in_identities
Revises: 0024_care_access_grants
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0025_sign_in_identities"
down_revision: str | None = "0024_care_access_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.create_table(
        "auth_flow_tokens",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auth_flow_tokens_token_hash", "auth_flow_tokens", ["token_hash"], unique=True)
    op.create_index("ix_auth_flow_tokens_expires_at", "auth_flow_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_flow_tokens_expires_at", table_name="auth_flow_tokens")
    op.drop_index("ix_auth_flow_tokens_token_hash", table_name="auth_flow_tokens")
    op.drop_table("auth_flow_tokens")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
