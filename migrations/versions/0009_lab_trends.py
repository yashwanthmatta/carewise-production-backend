"""Add lab trends.

Revision ID: 0009_lab_trends
Revises: 0008_email_verification
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0009_lab_trends"
down_revision: str | None = "0008_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lab_trends",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("patient_id", sa.String(length=80), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("report_id", sa.String(length=80), sa.ForeignKey("report_uploads.id"), nullable=True),
        sa.Column("test_name", sa.String(length=160), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("observed_on", sa.String(length=40), nullable=False),
        sa.Column("flag", sa.String(length=80), nullable=False),
        sa.Column("encrypted_notes", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lab_trends_patient_id", "lab_trends", ["patient_id"])
    op.create_index("ix_lab_trends_report_id", "lab_trends", ["report_id"])
    op.create_index("ix_lab_trends_test_name", "lab_trends", ["test_name"])
    op.create_index("ix_lab_trends_observed_on", "lab_trends", ["observed_on"])
    op.create_index("ix_lab_trends_flag", "lab_trends", ["flag"])
    op.create_index("ix_lab_trends_source", "lab_trends", ["source"])
    op.create_index("idx_lab_trends_patient_observed", "lab_trends", ["patient_id", sa.text("observed_on DESC")])
    op.create_index("idx_lab_trends_patient_test", "lab_trends", ["patient_id", "test_name"])


def downgrade() -> None:
    op.drop_index("idx_lab_trends_patient_test", table_name="lab_trends")
    op.drop_index("idx_lab_trends_patient_observed", table_name="lab_trends")
    op.drop_index("ix_lab_trends_source", table_name="lab_trends")
    op.drop_index("ix_lab_trends_flag", table_name="lab_trends")
    op.drop_index("ix_lab_trends_observed_on", table_name="lab_trends")
    op.drop_index("ix_lab_trends_test_name", table_name="lab_trends")
    op.drop_index("ix_lab_trends_report_id", table_name="lab_trends")
    op.drop_index("ix_lab_trends_patient_id", table_name="lab_trends")
    op.drop_table("lab_trends")
