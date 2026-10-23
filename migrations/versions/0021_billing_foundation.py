"""Billing foundation: processed provider events and store subscription expiry.

Additive only: one new table and one nullable column.

Revision ID: 0021_billing_foundation
Revises: 0020_patient_qa_opt_in
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0021_billing_foundation"
down_revision: str | None = "0020_patient_qa_opt_in"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("subscription_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_events_provider_event"),
    )


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_column("subscriptions", "expires_at")
