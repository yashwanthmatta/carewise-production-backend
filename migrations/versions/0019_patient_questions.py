"""Patient follow-up questions on approved DocBridge packets.

Revision ID: 0019_patient_questions
Revises: 0018_draft_edits
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0019_patient_questions"
down_revision: str | None = "0018_draft_edits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_questions",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("packet_id", sa.String(length=80), nullable=False),
        sa.Column("clinic_id", sa.String(length=80), nullable=False),
        sa.Column("encrypted_question", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("citations", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("deflected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_patient_questions_packet_id", "patient_questions", ["packet_id"])
    op.create_index("ix_patient_questions_clinic_id", "patient_questions", ["clinic_id"])
    op.create_index("ix_patient_questions_created_at", "patient_questions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_patient_questions_created_at", table_name="patient_questions")
    op.drop_index("ix_patient_questions_clinic_id", table_name="patient_questions")
    op.drop_index("ix_patient_questions_packet_id", table_name="patient_questions")
    op.drop_table("patient_questions")
