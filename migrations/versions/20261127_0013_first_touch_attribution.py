"""First-touch attribution snapshot, Deep2K ids and landing path, on checkout sessions and the orders made from
them. The existing utm_*/click_provider/click_id columns remain "last touch" (see CheckoutSession.first_touch).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _add_columns(table: str) -> None:
    # JSON can't take a DDL-level DEFAULT on every MySQL-wire-compatible database (see migration 0010), so it's
    # added nullable, backfilled, then tightened -- the plain-string columns take a server_default directly.
    op.add_column(table, sa.Column("first_touch", sa.JSON(), nullable=True))
    op.execute(f"UPDATE {table} SET first_touch = '{{}}' WHERE first_touch IS NULL")
    op.alter_column(table, "first_touch", existing_type=sa.JSON(), nullable=False)
    # 200, matching ShopifyCartIn's Text200 cap at the API layer -- a narrower column would silently truncate a
    # long id, risking two distinct ids colliding into the same stored value.
    op.add_column(table, sa.Column("deep2k_anonymous_id", sa.String(length=200), nullable=False, server_default=""))
    op.add_column(table, sa.Column("deep2k_session_id", sa.String(length=200), nullable=False, server_default=""))
    op.add_column(table, sa.Column("landing_path", sa.String(length=300), nullable=False, server_default=""))


def _drop_columns(table: str) -> None:
    op.drop_column(table, "landing_path")
    op.drop_column(table, "deep2k_session_id")
    op.drop_column(table, "deep2k_anonymous_id")
    op.drop_column(table, "first_touch")


def upgrade() -> None:
    _add_columns("checkout_sessions")
    _add_columns("orders")


def downgrade() -> None:
    _drop_columns("orders")
    _drop_columns("checkout_sessions")
