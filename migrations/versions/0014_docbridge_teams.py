"""DocBridge teams and review records: clinic invites, original draft and edited flag.

Revision ID: 0014_docbridge_teams
Revises: 0013_docbridge
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0014_docbridge_teams"
down_revision: str | None = "0013_docbridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lab_packets", sa.Column("encrypted_draft", sa.Text(), nullable=False, server_default=""))
    op.add_column("lab_packets", sa.Column("edited", sa.Integer(), nullable=True))
    op.create_table(
        "clinic_invites",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("clinic_id", sa.String(length=80), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="clinician"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clinic_invites_clinic_id", "clinic_invites", ["clinic_id"])
    op.create_index("ix_clinic_invites_code_hash", "clinic_invites", ["code_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("clinic_invites")
    op.drop_column("lab_packets", "edited")
    op.drop_column("lab_packets", "encrypted_draft")
