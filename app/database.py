"""SQLAlchemy engine and session management."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    connect_args = {"ssl": {"check_hostname": True}} if settings.db_ssl else {}
    return create_engine(
        settings.sqlalchemy_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_size,
        pool_pre_ping=True,  # transparently replace connections dropped by the server
        pool_recycle=1800,
        connect_args=connect_args,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def reset_engine_cache() -> None:
    """Forget the cached engine/factory (used when the configuration changes, e.g. in tests)."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def ensure_database_exists() -> None:
    """Best-effort ``CREATE DATABASE IF NOT EXISTS`` (needs the privilege; failures are ignored)."""
    url = make_url(get_settings().sqlalchemy_url)
    if not url.database:
        return
    try:
        # Connect to a schema that always exists; "no database" can't be expressed with URL.set().
        engine = create_engine(url.set(database="information_schema"))
        with engine.begin() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{url.database}` CHARACTER SET utf8mb4"))
        engine.dispose()
    except Exception as exc:
        log.debug("Could not auto-create database: %s", exc)


def wait_for_database(timeout_seconds: int = 30) -> None:
    """Block until MySQL accepts connections (e.g. while a container is still starting)."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Cannot connect to MySQL: {last_error}")


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one transaction per request (commit on success, rollback on error)."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaction scope for code running outside a request (worker, CLI)."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
