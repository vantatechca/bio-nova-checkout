"""Retain each order item's compare-at (MSRP) price, so it survives past the checkout session.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A plain integer DEFAULT is supported on every MySQL-wire-compatible database (unlike JSON defaults,
    # see migration 0010), so this can be added directly rather than via the nullable-then-backfill dance.
    op.add_column("order_items", sa.Column("compare_at_amount", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("order_items", "compare_at_amount")
