"""Clinic opt-in for patient follow-up questions (off by default).

Revision ID: 0020_patient_qa_opt_in
Revises: 0019_patient_questions
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0020_patient_qa_opt_in"
down_revision: str | None = "0019_patient_questions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinics", sa.Column("patient_qa_enabled", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("clinics", "patient_qa_enabled")
