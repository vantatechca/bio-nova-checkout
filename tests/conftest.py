"""Integration-test fixtures. These tests run against a real MySQL (set TEST_DATABASE_URL, e.g.

docker run -d -e MYSQL_ROOT_PASSWORD=testpw -p 3307:3306 mysql:8.4
TEST_DATABASE_URL=mysql+pymysql://root:testpw@127.0.0.1:3307/checkout_pytest pytest
"""

from __future__ import annotations

import os

# Configure the app *before* it is imported anywhere (settings are cached on first use).
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "mysql+pymysql://root:testpw@127.0.0.1:3307/checkout_pytest")
os.environ.update(
    DATABASE_URL=TEST_DB_URL,
    ADMIN_PASSWORD="test-admin-pw",
    WORKER_ENABLED="false",
    PUBLIC_URL="http://testserver",
)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import ensure_database_exists, get_engine, session_scope  # noqa: E402
from app.security import login_limiter, shopify_limiter  # noqa: E402
from app.services.config import config_service, ensure_defaults  # noqa: E402
from tests.helpers import Harness  # noqa: E402
from tests.support import FakeClientPaymentApi, FakeShopify, FakeSmtpServer, WebhookReceiver  # noqa: E402

TABLES_TO_CLEAR = (
    "order_items",
    "order_events",
    "orders",
    "checkout_sessions",
    "visits",
    "email_log",
    "webhook_deliveries",
    "settings",
    "stores",
)


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    from app.main import create_app

    try:
        ensure_database_exists()
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"MySQL is not reachable at TEST_DATABASE_URL: {exc}")
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_state(client: TestClient) -> None:
    """Every test starts from an empty database with default settings."""
    with get_engine().begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in TABLES_TO_CLEAR:
            conn.execute(text(f"TRUNCATE TABLE `{table}`"))
        conn.execute(text("ALTER TABLE orders AUTO_INCREMENT = 1001"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    with session_scope() as db:
        ensure_defaults(db)
    config_service.invalidate()
    login_limiter._failures.clear()
    shopify_limiter.clear()


@pytest.fixture
def h(client: TestClient) -> Harness:
    return Harness(client)


@pytest.fixture
def smtp_server() -> Iterator[FakeSmtpServer]:
    server = FakeSmtpServer()
    yield server
    server.close()


@pytest.fixture
def webhook_receiver() -> Iterator[WebhookReceiver]:
    receiver = WebhookReceiver()
    yield receiver
    receiver.close()


@pytest.fixture
def shopify(monkeypatch) -> Iterator[FakeShopify]:
    """A fake Shopify that the app talks to instead of https://<shop>.myshopify.com."""
    from app.config import get_settings

    fake = FakeShopify()
    monkeypatch.setattr(get_settings(), "shopify_api_base_url", fake.url)
    yield fake
    fake.close()


@pytest.fixture
def client_api() -> Iterator[FakeClientPaymentApi]:
    """The client's charge endpoint (see docs/client-payment-api.md)."""
    fake = FakeClientPaymentApi()
    yield fake
    fake.close()
