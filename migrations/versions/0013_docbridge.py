"""Add DocBridge: clinics, clinic members and clinician-approved lab packets.

Revision ID: 0013_docbridge
Revises: 0012_doctor_shares
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0013_docbridge"
down_revision: str | None = "0012_doctor_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinics",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("tone", sa.String(length=20), nullable=False, server_default="friendly"),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("owner_user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clinics_owner_user_id", "clinics", ["owner_user_id"])
    op.create_table(
        "clinic_members",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("clinic_id", sa.String(length=80), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="clinician"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("clinic_id", "user_id", name="uq_clinic_members_clinic_user"),
    )
    op.create_index("ix_clinic_members_clinic_id", "clinic_members", ["clinic_id"])
    op.create_index("ix_clinic_members_user_id", "clinic_members", ["user_id"])
    op.create_table(
        "lab_packets",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("clinic_id", sa.String(length=80), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("patient_ref_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_patient_ref", sa.Text(), nullable=False),
        sa.Column("lab_date", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("encrypted_markers", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_questions", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("approved_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("approved_by_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_seconds", sa.Integer(), nullable=True),
        sa.Column("patient_token_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("patient_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lab_packets_clinic_id", "lab_packets", ["clinic_id"])
    op.create_index("ix_lab_packets_patient_ref_hash", "lab_packets", ["patient_ref_hash"])
    op.create_index("ix_lab_packets_status", "lab_packets", ["status"])
    op.create_index("ix_lab_packets_patient_token_hash", "lab_packets", ["patient_token_hash"])


def downgrade() -> None:
    op.drop_table("lab_packets")
    op.drop_table("clinic_members")
    op.drop_table("clinics")
