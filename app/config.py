"""Environment-driven application configuration (12-factor)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Process-level settings.

    Business settings (store name, payment methods, SMTP...) are editable at runtime in the
    admin and live in the database instead.
    """

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # --- HTTP
    host: str = "0.0.0.0"
    port: int = 3000
    public_url: str | None = None  # e.g. https://checkout.example.com; used to build checkout links
    trust_proxy: bool = False  # honour X-Forwarded-For when behind a reverse proxy

    # --- Database: either DATABASE_URL or the DB_* parts
    database_url: str | None = None
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "checkout"
    db_ssl: bool = False
    db_pool_size: int = 10
    auto_migrate: bool = True  # run `alembic upgrade head` on startup

    # --- Admin
    admin_password: str | None = None  # generated (and printed) at startup when unset
    admin_token_ttl_hours: int = 12

    # --- Checkout
    session_ttl_hours: int = 24

    # --- Shopify connector
    # Override of https://<shop-domain> for the Storefront API. For local development / tests with a fake Shopify only.
    shopify_api_base_url: str | None = None

    # --- Card payments
    # The fake "mock" card provider approves any test card. It is refused on a public https site unless this is set.
    allow_test_card_provider: bool = False

    # --- Background worker (webhook + email delivery)
    worker_enabled: bool = True
    worker_interval_seconds: float = 2.0

    @property
    def sqlalchemy_url(self) -> str:
        """Normalised SQLAlchemy URL using the PyMySQL driver."""
        if self.database_url:
            url = self.database_url
            for prefix in ("mysql://", "mysql+mysqlconnector://"):
                if url.startswith(prefix):
                    url = "mysql+pymysql://" + url[len(prefix) :]
            if "charset=" not in url:
                url += ("&" if "?" in url else "?") + "charset=utf8mb4"
            return url
        return (
            f"mysql+pymysql://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
