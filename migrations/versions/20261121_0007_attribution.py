"""Ad attribution: UTM parameters and ad-click ids, carried from checkout session to order.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_COLUMNS = [
    ("utm_source", sa.String(length=100)),
    ("utm_medium", sa.String(length=100)),
    ("utm_campaign", sa.String(length=200)),
    ("utm_content", sa.String(length=200)),
    ("utm_term", sa.String(length=200)),
    ("click_provider", sa.String(length=20)),
    ("click_id", sa.String(length=200)),
]


def upgrade() -> None:
    for table in ("checkout_sessions", "orders"):
        for name, col_type in _COLUMNS:
            op.add_column(table, sa.Column(name, col_type, nullable=False, server_default=""))
    op.create_index("ix_orders_utm_campaign", "orders", ["utm_campaign"])
    op.create_index("ix_checkout_sessions_utm_campaign", "checkout_sessions", ["utm_campaign"])


def downgrade() -> None:
    op.drop_index("ix_checkout_sessions_utm_campaign", table_name="checkout_sessions")
    op.drop_index("ix_orders_utm_campaign", table_name="orders")
    for table in ("checkout_sessions", "orders"):
        for name, _ in reversed(_COLUMNS):
            op.drop_column(table, name)
