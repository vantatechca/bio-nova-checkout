"""Multi-store: a ``stores`` table; sessions, orders and visits now belong to a store.

The legacy single-store configuration (``settings`` row ``k='store'``) becomes store #1, keeping its API key so
existing integrations continue to work. Existing rows are assigned to that store.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

import json
import re
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SCOPED_TABLES = ("checkout_sessions", "orders", "visits")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60] or "default"


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("api_key", sa.String(length=80), nullable=False),
        sa.Column("shopify_domain", sa.String(length=255), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stores")),
        sa.UniqueConstraint("api_key", name=op.f("uq_stores_api_key")),
        sa.UniqueConstraint("shopify_domain", name=op.f("uq_stores_shopify_domain")),
        sa.UniqueConstraint("slug", name=op.f("uq_stores_slug")),
    )

    conn = op.get_bind()
    row = conn.execute(sa.text("SELECT v FROM settings WHERE k = 'store'")).first()
    have_store = row is not None
    if have_store:
        value = row[0]
        data = json.loads(value) if isinstance(value, (str, bytes)) else dict(value)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        conn.execute(
            sa.text(
                "INSERT INTO stores (id, slug, name, active, api_key, shopify_domain, settings, created_at, updated_at) "
                "VALUES (1, :slug, :name, 1, :api_key, :domain, :settings, :now, :now)"
            ),
            {
                "slug": _slug(data.get("storeName", "")),
                "name": (data.get("storeName") or "Default")[:100],
                "api_key": data.get("apiKey") or "migrated-key-1",
                "domain": data.get("shopifyDomain") or None,
                "settings": json.dumps(data),
                "now": now,
            },
        )
        conn.execute(sa.text("DELETE FROM settings WHERE k = 'store'"))

    for table in SCOPED_TABLES:
        op.add_column(table, sa.Column("store_id", sa.BigInteger(), nullable=True))
        if have_store:
            conn.execute(sa.text(f"UPDATE {table} SET store_id = 1"))
        op.alter_column(table, "store_id", existing_type=sa.BigInteger(), nullable=False)
        op.create_index(op.f(f"ix_{table}_store_id"), table, ["store_id"], unique=False)
        op.create_foreign_key(op.f(f"fk_{table}_store_id_stores"), table, "stores", ["store_id"], ["id"])


def downgrade() -> None:
    conn = op.get_bind()
    first = conn.execute(sa.text("SELECT settings FROM stores ORDER BY id LIMIT 1")).first()

    for table in SCOPED_TABLES:
        op.drop_constraint(op.f(f"fk_{table}_store_id_stores"), table, type_="foreignkey")
        op.drop_index(op.f(f"ix_{table}_store_id"), table_name=table)
        op.drop_column(table, "store_id")

    if first is not None:
        value = first[0]
        data = value if isinstance(value, str) else json.dumps(value)
        conn.execute(sa.text("INSERT INTO settings (k, v) VALUES ('store', :v)"), {"v": data})
    op.drop_table("stores")
