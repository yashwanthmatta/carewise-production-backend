"""Clinic visit-summary settings: self-pay prices, hidden sections, coverage checklist.

Additive only: three new columns on clinics.

Revision ID: 0022_clinic_visit_settings
Revises: 0021_billing_foundation
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0022_clinic_visit_settings"
down_revision: str | None = "0021_billing_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinics", sa.Column("self_pay_prices", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("clinics", sa.Column("prices_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clinics", sa.Column("visit_options", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("clinics", "visit_options")
    op.drop_column("clinics", "prices_updated_at")
    op.drop_column("clinics", "self_pay_prices")
