"""Flag visits and checkout sessions from configured internal/non-customer traffic, as a reporting breakdown
(never a silent drop of the underlying rows).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A plain "0" default (like migration 0011's BigInteger default) is supported on every MySQL-wire-compatible
    # database; sa.false() renders as the FALSE keyword, which is unnecessary risk for the same result.
    op.add_column("visits", sa.Column("is_internal", sa.Boolean(), nullable=False, server_default="0"))
    op.create_index("ix_visits_internal", "visits", ["is_internal"])

    op.add_column("checkout_sessions", sa.Column("is_internal", sa.Boolean(), nullable=False, server_default="0"))
    op.create_index("ix_checkout_sessions_internal", "checkout_sessions", ["is_internal"])


def downgrade() -> None:
    op.drop_index("ix_checkout_sessions_internal", table_name="checkout_sessions")
    op.drop_column("checkout_sessions", "is_internal")

    op.drop_index("ix_visits_internal", table_name="visits")
    op.drop_column("visits", "is_internal")
