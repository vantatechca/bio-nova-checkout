"""Checkout step milestones (form started, contact done, ... pay clicked), for a deeper conversion funnel.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

import app.models.types

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checkout_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("at", app.models.types.UTCDateTime(), nullable=False),
        sa.Column("step", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name=op.f("fk_checkout_events_store_id_stores")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checkout_events")),
    )
    op.create_index("ix_checkout_events_session_step", "checkout_events", ["session_id", "step"], unique=True)
    op.create_index("ix_checkout_events_store_id", "checkout_events", ["store_id"])


def downgrade() -> None:
    op.drop_index("ix_checkout_events_store_id", table_name="checkout_events")
    op.drop_index("ix_checkout_events_session_step", table_name="checkout_events")
    op.drop_table("checkout_events")
