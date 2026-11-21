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

    # --- Content panels (admin pages fed by a bot). One key per panel, set only here, never in the database.
    # A panel whose key is unset is switched off: its API answers 404 like any unknown path.
    ads_data_key: str | None = None
    sites_key: str | None = None
    panel_allowed_ips: str = ""  # optional comma-separated allowlist for the panel API; empty = any address

    # --- Background worker (webhook + email delivery)
    worker_enabled: bool = True
    worker_interval_seconds: float = 2.0

    # --- Visitor IP / geolocation / fraud signals (see docs on visit analytics)
    # off: nothing is stored. truncated (default): IPv4 to /24, IPv6 to /48. full: the complete address -- only
    # turn this on once you've considered the data-protection implications; the visitor hash always uses the
    # full IP regardless of this setting, so unique-visitor counts aren't affected by it.
    visit_ip_mode: str = "truncated"
    geoip_city_db: str = ""  # path to a GeoLite2-City.mmdb; empty disables country/city lookups
    geoip_asn_db: str = ""  # path to a GeoLite2-ASN.mmdb; empty disables ASN/ISP lookups and the datacenter flag
    risk_datacenter_asns: str = ""  # comma-separated ASN numbers (e.g. "AS14061,AS16509") flagged as datacenter/VPN
    checkout_rate_limit: int = 30  # order placements allowed per IP per minute

    @property
    def panel_ip_allowlist(self) -> frozenset[str]:
        return frozenset(ip.strip() for ip in self.panel_allowed_ips.split(",") if ip.strip())

    @property
    def ip_mode(self) -> str:
        return self.visit_ip_mode if self.visit_ip_mode in ("off", "truncated", "full") else "truncated"

    @property
    def risk_asn_set(self) -> frozenset[str]:
        return frozenset(asn.strip() for asn in self.risk_datacenter_asns.split(",") if asn.strip())

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
