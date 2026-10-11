"""Two-step sign-in (authenticator app codes and recovery codes).

Revision ID: 0016_two_step_sign_in
Revises: 0015_medicine_reminders
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0016_two_step_sign_in"
down_revision: str | None = "0015_medicine_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("encrypted_totp_secret", sa.Text(), nullable=False, server_default=""))
    op.add_column("users", sa.Column("totp_enabled", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("totp_last_step", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("recovery_code_hashes", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("users", "recovery_code_hashes")
    op.drop_column("users", "totp_last_step")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "encrypted_totp_secret")
