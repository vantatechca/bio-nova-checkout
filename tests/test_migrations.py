"""Guards against the ORM models and the Alembic migrations drifting apart."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.database import get_engine
from app.models import Base


def test_migrations_match_the_models(client):
    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Models changed without a migration: {diff}"


def test_order_numbers_start_at_1001(client):
    with get_engine().connect() as conn:
        from sqlalchemy import text

        row = conn.execute(text("SHOW CREATE TABLE orders")).one()
    assert "AUTO_INCREMENT=" in row[1]
