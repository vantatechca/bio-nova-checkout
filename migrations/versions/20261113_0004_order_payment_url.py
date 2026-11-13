"""Remember the payment page an order was sent to, so a customer who comes back can continue paying.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "payment_url")
