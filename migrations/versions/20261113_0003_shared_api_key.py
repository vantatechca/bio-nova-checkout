"""The API key is now shared by all stores, so ``stores.api_key`` goes away.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_stores_api_key", "stores", type_="unique")
    op.drop_column("stores", "api_key")


def downgrade() -> None:
    op.add_column("stores", sa.Column("api_key", sa.String(length=80), nullable=True))
    op.execute("UPDATE stores SET api_key = CONCAT('restored-key-', id)")
    op.alter_column("stores", "api_key", existing_type=sa.String(length=80), nullable=False)
    op.create_unique_constraint("uq_stores_api_key", "stores", ["api_key"])
