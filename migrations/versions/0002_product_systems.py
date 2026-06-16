"""Add product systems for reports, subscriptions, and notifications.

Revision ID: 0002_product_systems
Revises: 0001_initial_schema
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_product_systems"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_uploads",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("patient_id", sa.String(length=80), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("uploaded_by", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("storage_url", sa.Text(), nullable=False),
        sa.Column("encrypted_report_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_report_uploads_patient_id", "report_uploads", ["patient_id"])
    op.create_index("ix_report_uploads_uploaded_by", "report_uploads", ["uploaded_by"])
    op.create_index("ix_report_uploads_status", "report_uploads", ["status"])

    op.create_table(
        "report_analyses",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("report_id", sa.String(length=80), sa.ForeignKey("report_uploads.id"), nullable=False),
        sa.Column("patient_id", sa.String(length=80), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("risk_level", sa.String(length=80), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("recommendations_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_report_analyses_report_id", "report_analyses", ["report_id"])
    op.create_index("ix_report_analyses_patient_id", "report_analyses", ["patient_id"])
    op.create_index("ix_report_analyses_risk_level", "report_analyses", ["risk_level"])
    op.create_index("ix_report_analyses_status", "report_analyses", ["status"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_code", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("payment_provider", sa.String(length=80), nullable=False),
        sa.Column("provider_reference", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_plan_code", "subscriptions", ["plan_code"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("device_token", sa.Text(), nullable=False),
        sa.Column("enabled", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])

    op.create_index("idx_reports_patient_created", "report_uploads", ["patient_id", sa.text("created_at DESC")])
    op.create_index("idx_analyses_patient_created", "report_analyses", ["patient_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_analyses_patient_created", table_name="report_analyses")
    op.drop_index("idx_reports_patient_created", table_name="report_uploads")
    op.drop_table("notification_preferences")
    op.drop_table("subscriptions")
    op.drop_table("report_analyses")
    op.drop_table("report_uploads")
