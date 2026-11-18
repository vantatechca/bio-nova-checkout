"""Content panels: stored sections, their version history and the per-key activity log.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

import app.models.types

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "panel_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("panel", sa.String(length=32), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("pending_payload", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", app.models.types.UTCDateTime(), nullable=True),
        sa.Column("created_at", app.models.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.models.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_panel_items")),
        sa.UniqueConstraint("panel", "section", name="uq_panel_items_panel_section"),
    )
    op.create_table(
        "panel_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("panel", sa.String(length=32), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", app.models.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_panel_versions")),
        sa.UniqueConstraint("panel", "section", "version", name="uq_panel_versions_panel_section_version"),
    )
    op.create_table(
        "panel_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("panel", sa.String(length=32), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("created_at", app.models.types.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_panel_log")),
    )
    op.create_index("ix_panel_log_actor_created_at", "panel_log", ["actor", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_panel_log_actor_created_at", table_name="panel_log")
    op.drop_table("panel_log")
    op.drop_table("panel_versions")
    op.drop_table("panel_items")
