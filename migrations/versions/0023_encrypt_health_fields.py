"""Make room for encrypted health fields.

Widens the health columns that are now encrypted by the application (results summaries, care
plans, lab tracker values, intake goals, some profile fields, report file names, deletion
reasons) to TEXT, and drops the indexes on lab test name, lab flag and region: those columns
now hold ciphertext, which cannot be searched, so the indexes would only cost space.

No data is changed. Existing plaintext rows stay readable and are encrypted later by
`scripts/security/encrypt_fields.py` (dry run first; see docs/security-hardening/encryption-migration.md).

Revision ID: 0023_encrypt_health_fields
Revises: 0022_clinic_visit_settings
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0023_encrypt_health_fields"
down_revision: str | None = "0022_clinic_visit_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column, previous type). Columns that were already TEXT need no change.
WIDENED = [
    ("patient_profiles", "sex_at_birth", sa.String(40)),
    ("patient_profiles", "location_region", sa.String(120)),
    ("patient_profiles", "insurance_status", sa.String(80)),
    ("intakes", "diet_style", sa.String(80)),
    ("intakes", "activity_level", sa.String(80)),
    ("report_uploads", "file_name", sa.String(255)),
    ("lab_trends", "test_name", sa.String(160)),
    ("lab_trends", "value", sa.String(80)),
    ("lab_trends", "unit", sa.String(80)),
    ("lab_trends", "flag", sa.String(80)),
]

DROPPED_INDEXES = [
    ("ix_patient_profiles_location_region", "patient_profiles", ["location_region"]),
    ("ix_lab_trends_test_name", "lab_trends", ["test_name"]),
    ("ix_lab_trends_flag", "lab_trends", ["flag"]),
    ("idx_lab_trends_patient_test", "lab_trends", ["patient_id", "test_name"]),
]


def upgrade() -> None:
    for name, _, _ in DROPPED_INDEXES:
        # IF EXISTS: databases first built with create_all may not have every named index.
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for table, column, previous in WIDENED:
        # batch mode so the same migration also runs on SQLite (local development and tests).
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, type_=sa.Text(), existing_type=previous)


def downgrade() -> None:
    # Only safe before any row has been encrypted: ciphertext does not fit the old widths.
    # Decrypt first with `scripts/security/encrypt_fields.py --apply --to-plaintext` (see the migration doc).
    for table, column, previous in WIDENED:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, type_=previous, existing_type=sa.Text())
    for name, table, columns in DROPPED_INDEXES:
        op.create_index(name, table, columns)
