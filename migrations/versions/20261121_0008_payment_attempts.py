"""Payment attempts: every charge try (succeeded, declined or errored), so declines can be reported on.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

import app.models.types

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("at", app.models.types.UTCDateTime(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("method_id", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name=op.f("fk_payment_attempts_store_id_stores")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_attempts")),
    )
    op.create_index("ix_payment_attempts_session", "payment_attempts", ["session_id"])
    op.create_index("ix_payment_attempts_at", "payment_attempts", ["at"])
    op.create_index("ix_payment_attempts_store_id", "payment_attempts", ["store_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_attempts_store_id", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_at", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_session", table_name="payment_attempts")
    op.drop_table("payment_attempts")
