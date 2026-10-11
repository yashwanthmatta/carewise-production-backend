"""DocBridge email intake: clinic intake address and emailed lab files.

Revision ID: 0017_email_intake
Revises: 0016_two_step_sign_in
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0017_email_intake"
down_revision: str | None = "0016_two_step_sign_in"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinics", sa.Column("intake_code", sa.String(length=24), nullable=True))
    op.create_index("ix_clinics_intake_code", "clinics", ["intake_code"], unique=True)
    op.add_column("lab_packets", sa.Column("source", sa.String(length=10), nullable=False, server_default="manual"))
    op.add_column("lab_packets", sa.Column("encrypted_source_text", sa.Text(), nullable=False, server_default=""))
    op.add_column("lab_packets", sa.Column("file_key", sa.String(length=300), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("lab_packets", "file_key")
    op.drop_column("lab_packets", "encrypted_source_text")
    op.drop_column("lab_packets", "source")
    op.drop_index("ix_clinics_intake_code", table_name="clinics")
    op.drop_column("clinics", "intake_code")
