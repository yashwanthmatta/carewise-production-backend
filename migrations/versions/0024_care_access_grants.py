"""Care-team grants: a patient lets a named clinician see their records.

Additive only: one new table. Access rules change in code (app/services/access_control.py);
CAREWISE_STAFF_ACCESS_MODE=legacy_global restores the old global staff access if needed.

Revision ID: 0024_care_access_grants
Revises: 0023_encrypt_health_fields
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0024_care_access_grants"
down_revision: str | None = "0023_encrypt_health_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "care_access_grants",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("patient_id", sa.String(length=80), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("staff_user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("granted_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_care_access_grants_patient_id", "care_access_grants", ["patient_id"])
    op.create_index("ix_care_access_grants_staff_user_id", "care_access_grants", ["staff_user_id"])
    op.create_index("idx_care_grants_staff_patient", "care_access_grants", ["staff_user_id", "patient_id"])


def downgrade() -> None:
    op.drop_index("idx_care_grants_staff_patient", table_name="care_access_grants")
    op.drop_index("ix_care_access_grants_staff_user_id", table_name="care_access_grants")
    op.drop_index("ix_care_access_grants_patient_id", table_name="care_access_grants")
    op.drop_table("care_access_grants")
