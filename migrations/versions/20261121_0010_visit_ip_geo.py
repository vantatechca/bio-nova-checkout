"""Visitor IP (truncated by default, see VISIT_IP_MODE) and geolocation on visits; origin + risk flags on orders.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("visits", sa.Column("ip", sa.String(length=45), nullable=False, server_default=""))
    op.add_column("visits", sa.Column("country", sa.String(length=2), nullable=False, server_default=""))
    op.add_column("visits", sa.Column("city", sa.String(length=100), nullable=False, server_default=""))
    op.add_column("visits", sa.Column("asn", sa.BigInteger(), nullable=True))
    op.add_column("visits", sa.Column("isp", sa.String(length=200), nullable=False, server_default=""))
    op.create_index("ix_visits_ip", "visits", ["ip"])

    op.add_column("orders", sa.Column("order_ip", sa.String(length=45), nullable=False, server_default=""))
    op.add_column("orders", sa.Column("order_country", sa.String(length=2), nullable=False, server_default=""))
    # JSON/TEXT/BLOB columns couldn't take a DDL-level DEFAULT before MySQL 8.0.13, and TiDB's support for that
    # specific feature isn't guaranteed either -- so this adds it nullable, backfills, then tightens it, which
    # works the same way on every MySQL-wire-compatible database regardless of that feature's availability.
    op.add_column("orders", sa.Column("risk_flags", sa.JSON(), nullable=True))
    op.execute("UPDATE orders SET risk_flags = '{}' WHERE risk_flags IS NULL")
    op.alter_column("orders", "risk_flags", existing_type=sa.JSON(), nullable=False)
    op.create_index("ix_orders_ip", "orders", ["order_ip"])


def downgrade() -> None:
    op.drop_index("ix_orders_ip", table_name="orders")
    op.drop_column("orders", "risk_flags")
    op.drop_column("orders", "order_country")
    op.drop_column("orders", "order_ip")

    op.drop_index("ix_visits_ip", table_name="visits")
    op.drop_column("visits", "isp")
    op.drop_column("visits", "asn")
    op.drop_column("visits", "city")
    op.drop_column("visits", "country")
    op.drop_column("visits", "ip")
