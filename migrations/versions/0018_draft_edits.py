"""DocBridge draft edits (doctor preference pairs) and model versions.

Revision ID: 0018_draft_edits
Revises: 0017_email_intake
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0018_draft_edits"
down_revision: str | None = "0017_email_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lab_packets", sa.Column("encrypted_draft_questions", sa.Text(), nullable=False, server_default=""))
    op.add_column("lab_packets", sa.Column("model_version", sa.String(length=80), nullable=False, server_default=""))
    op.add_column("lab_packets", sa.Column("prompt_version", sa.String(length=80), nullable=False, server_default=""))
    op.create_table(
        "draft_edits",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("packet_id", sa.String(length=80), nullable=False),
        sa.Column("clinic_id", sa.String(length=80), nullable=False),
        sa.Column("doctor_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("event", sa.String(length=10), nullable=False, server_default="save"),
        sa.Column("encrypted_original_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_edited_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("edited_sections", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("edit_distance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zero_edit_approval", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_version", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_draft_edits_packet_id", "draft_edits", ["packet_id"])
    op.create_index("ix_draft_edits_clinic_id", "draft_edits", ["clinic_id"])
    op.create_index("ix_draft_edits_created_at", "draft_edits", ["created_at"])
    versions = op.create_table(
        "model_versions",
        sa.Column("version", sa.String(length=80), primary_key=True),
        sa.Column("base_model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("training_pairs_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("training_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="canary"),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(versions, [{"version": "docbridge-rules-v1", "base_model": "rule-based drafting on the clinician's device", "training_pairs_count": 0, "status": "prod"}])


def downgrade() -> None:
    op.drop_table("model_versions")
    op.drop_index("ix_draft_edits_created_at", table_name="draft_edits")
    op.drop_index("ix_draft_edits_clinic_id", table_name="draft_edits")
    op.drop_index("ix_draft_edits_packet_id", table_name="draft_edits")
    op.drop_table("draft_edits")
    op.drop_column("lab_packets", "prompt_version")
    op.drop_column("lab_packets", "model_version")
    op.drop_column("lab_packets", "encrypted_draft_questions")
