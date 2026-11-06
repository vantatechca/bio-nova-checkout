"""Programmatic Alembic access (``python -m app.migrate`` or automatically at startup)."""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from app.config import BASE_DIR


def alembic_config() -> Config:
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return config


def upgrade_to_head() -> None:
    command.upgrade(alembic_config(), "head")


if __name__ == "__main__":
    upgrade_to_head()
