"""Keep a styled HTML version of each queued email next to its plain-text body.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_log", sa.Column("html", sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"), nullable=True))


def downgrade() -> None:
    op.drop_column("email_log", "html")
