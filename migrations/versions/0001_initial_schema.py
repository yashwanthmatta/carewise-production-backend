"""Initial CareWise schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "patient_profiles",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("encrypted_name", sa.Text(), nullable=False),
        sa.Column("encrypted_date_of_birth", sa.Text(), nullable=False),
        sa.Column("sex_at_birth", sa.String(length=40), nullable=False),
        sa.Column("encrypted_conditions", sa.Text(), nullable=False),
        sa.Column("encrypted_allergies", sa.Text(), nullable=False),
        sa.Column("location_region", sa.String(length=120), nullable=False),
        sa.Column("insurance_status", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_patient_profiles_location_region", "patient_profiles", ["location_region"])
    op.create_index("ix_patient_profiles_user_id", "patient_profiles", ["user_id"])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("consent_type", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("accepted", sa.String(length=10), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consent_records_consent_type", "consent_records", ["consent_type"])
    op.create_index("ix_consent_records_region", "consent_records", ["region"])
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])
    op.create_index("ix_consent_records_version", "consent_records", ["version"])

    op.create_table(
        "medications",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("patient_id", sa.String(length=80), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("encrypted_name", sa.Text(), nullable=False),
        sa.Column("encrypted_dose", sa.Text(), nullable=False),
        sa.Column("encrypted_timing", sa.Text(), nullable=False),
        sa.Column("refill_date", sa.String(length=40), nullable=False),
        sa.Column("encrypted_notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_medications_patient_id", "medications", ["patient_id"])

    op.create_table(
        "intakes",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("patient_id", sa.String(length=80), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("encrypted_symptom_text", sa.Text(), nullable=False),
        sa.Column("goals_json", sa.Text(), nullable=False),
        sa.Column("diet_style", sa.String(length=80), nullable=False),
        sa.Column("activity_level", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_intakes_patient_id", "intakes", ["patient_id"])

    op.create_table(
        "care_plans",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("patient_id", sa.String(length=80), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("intake_id", sa.String(length=80), sa.ForeignKey("intakes.id"), nullable=False),
        sa.Column("risk_level", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("emergency_flags_json", sa.Text(), nullable=False),
        sa.Column("matched_conditions_json", sa.Text(), nullable=False),
        sa.Column("recommendation_json", sa.Text(), nullable=False),
        sa.Column("clinician_note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_care_plans_intake_id", "care_plans", ["intake_id"])
    op.create_index("ix_care_plans_patient_id", "care_plans", ["patient_id"])
    op.create_index("ix_care_plans_risk_level", "care_plans", ["risk_level"])
    op.create_index("ix_care_plans_status", "care_plans", ["status"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("actor_id", sa.String(length=80), nullable=False),
        sa.Column("patient_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_patient_id", "audit_events", ["patient_id"])

    op.create_index("idx_audit_patient_created", "audit_events", ["patient_id", sa.text("created_at DESC")])
    op.create_index("idx_care_plans_patient_created", "care_plans", ["patient_id", sa.text("created_at DESC")])
    op.create_index("idx_care_plans_status_created", "care_plans", ["status", sa.text("created_at DESC")])
    op.create_index("idx_consent_region_created", "consent_records", ["region", sa.text("created_at DESC")])
    op.create_index("idx_consent_user_created", "consent_records", ["user_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_consent_user_created", table_name="consent_records")
    op.drop_index("idx_consent_region_created", table_name="consent_records")
    op.drop_index("idx_care_plans_status_created", table_name="care_plans")
    op.drop_index("idx_care_plans_patient_created", table_name="care_plans")
    op.drop_index("idx_audit_patient_created", table_name="audit_events")

    op.drop_table("audit_events")
    op.drop_table("care_plans")
    op.drop_table("intakes")
    op.drop_table("medications")
    op.drop_table("consent_records")
    op.drop_table("patient_profiles")
    op.drop_table("users")
