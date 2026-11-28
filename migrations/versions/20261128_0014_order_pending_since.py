"""Track when an order entered (or re-entered) payment_status=pending, so a stuck redirect-flow payment can be
told apart from an offline/bank-transfer order that is *meant* to sit pending.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("pending_since", sa.DateTime(), nullable=True))
    # Backfill: every order currently pending has been pending since it was created (this column didn't exist
    # before, so there's no better answer) -- the sweep's own 24h window means an inaccurate backfill here only
    # ever makes an old pending order eligible for expiry sooner, never erases anything (orders are never deleted).
    op.execute("UPDATE orders SET pending_since = created_at WHERE payment_status = 'pending'")


def downgrade() -> None:
    op.drop_column("orders", "pending_since")
