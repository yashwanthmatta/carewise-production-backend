"""Medicine reminders with optional phone calls.

Revision ID: 0015_medicine_reminders
Revises: 0014_docbridge_teams
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0015_medicine_reminders"
down_revision: str | None = "0014_docbridge_teams"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medicine_reminders",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("encrypted_person", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_label", sa.Text(), nullable=False, server_default=""),
        sa.Column("times", sa.String(length=64), nullable=False),
        sa.Column("days", sa.String(length=40), nullable=False, server_default="daily"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="America/New_York"),
        sa.Column("language", sa.String(length=5), nullable=False, server_default="en"),
        sa.Column("encrypted_phone", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_caller_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("call_status", sa.String(length=20), nullable=False, server_default="off"),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alert_on_miss", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_medicine_reminders_user_id", "medicine_reminders", ["user_id"])
    op.create_table(
        "reminder_events",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("reminder_id", sa.String(length=80), sa.ForeignKey("medicine_reminders.id"), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False, server_default="dose"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="due"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reminder_id", "kind", "due_at", name="uq_reminder_event"),
    )
    op.create_index("ix_reminder_events_reminder_id", "reminder_events", ["reminder_id"])
    op.create_index("ix_reminder_events_due_at", "reminder_events", ["due_at"])
    op.create_index("ix_reminder_events_status", "reminder_events", ["status"])
    op.create_index("ix_reminder_events_token_hash", "reminder_events", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("reminder_events")
    op.drop_table("medicine_reminders")
