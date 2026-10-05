"""Store the Stripe customer id on subscriptions so people can manage billing.

Revision ID: 0011_subscription_customer
Revises: 0010_product_signals
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0011_subscription_customer"
down_revision: str | None = "0010_product_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("provider_customer", sa.String(length=160), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "provider_customer")
