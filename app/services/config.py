"""Runtime configuration stored in the database, with a short-lived in-process cache.

Each connected store (see ``Store``) carries its own ``StoreSettings``; e-mail (SMTP) settings are shared.
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import Store
from app.repositories import SettingsRepository, StoreRepository
from app.schemas.settings import SHARED_FIELDS, STORE_ONLY_FIELDS, EmailSettings, StoreSettings

_EMAIL, _SALT, _SECRET, _SHARED = "email", "salt", "secret", "shared"
_TTL_SECONDS = 5.0  # other app instances' edits become visible within this window


def allowed_origins(store: StoreSettings) -> set[str]:
    """Browser origins a store's storefront calls us from: its website (with/without ``www.``) and its shop domain."""
    origins: set[str] = set()
    candidates = [store.store_url, f"https://{store.shopify_domain}" if store.shopify_domain else ""]
    for url in candidates:
        parts = urlparse(url)
        if not (parts.scheme and parts.hostname):
            continue
        port = f":{parts.port}" if parts.port else ""
        host = parts.hostname
        alternate = host.removeprefix("www.") if host.startswith("www.") else f"www.{host}"
        origins.update({f"{parts.scheme}://{host}{port}", f"{parts.scheme}://{alternate}{port}"})
    return origins


@dataclass(frozen=True)
class StoreRecord:
    id: int
    slug: str
    name: str
    active: bool
    settings: StoreSettings

    @property
    def origins(self) -> set[str]:
        return allowed_origins(self.settings)


def merged_settings(own: dict, shared: dict) -> StoreSettings:
    """A store's full settings: its own (branding, Shopify) plus the settings shared by all stores."""
    return StoreSettings.model_validate({**own, **shared})


def split_settings(settings: StoreSettings) -> tuple[dict, dict]:
    """``(own, shared)`` as JSON-ready dicts, for saving the per-store row and the shared row separately."""
    return (
        settings.model_dump(by_alias=True, include=set(STORE_ONLY_FIELDS)),
        settings.model_dump(by_alias=True, include=set(SHARED_FIELDS)),
    )


def _record(row: Store, shared: dict) -> StoreRecord:
    return StoreRecord(
        id=row.id, slug=row.slug, name=row.name, active=row.active, settings=merged_settings(row.settings, shared)
    )


@dataclass(frozen=True)
class AppConfig:
    stores: tuple[StoreRecord, ...]
    email: EmailSettings
    salt: str  # salts the visitor hash (privacy-preserving unique-visitor counts)
    secret: str  # signs admin tokens

    @property
    def default_store(self) -> StoreRecord:
        """The first active store (else the first store): what single-store callers and the admin default to."""
        for store in self.stores:
            if store.active:
                return store
        return self.stores[0]

    def store_by_id(self, store_id: int) -> StoreRecord | None:
        return next((s for s in self.stores if s.id == store_id), None)

    def api_key_matches(self, key: str) -> bool:
        """The API key is shared by all stores. Constant-time comparison."""
        return hmac.compare_digest(self.default_store.settings.api_key.encode(), key.encode())

    def store_by_ref(self, ref: str) -> StoreRecord | None:
        """A store by id or slug (the ``X-Checkout-Store`` header)."""
        ref = ref.strip()
        return next((s for s in self.stores if str(s.id) == ref or s.slug == ref), None)

    def stores_for_origin(self, origin: str) -> list[StoreRecord]:
        return [s for s in self.stores if s.active and origin in s.origins]

    def stores_for_shop(self, shop: str) -> list[StoreRecord]:
        shop = shop.strip().lower()
        return [s for s in self.stores if s.active and shop and s.settings.shopify_domain.lower() == shop]


def mirror_columns(row: Store, settings: StoreSettings) -> None:
    """Saves the store's own settings and keeps the indexed columns on ``Store`` in step with them."""
    row.settings = split_settings(settings)[0]
    row.name = settings.store_name
    row.shopify_domain = settings.shopify_domain or None


def ensure_defaults(db: Session) -> None:
    """First-run seeding. Existing rows are never overwritten."""
    from app.services import stores  # local import: stores builds on this module

    repo = SettingsRepository(db)
    repo.insert_if_missing(_EMAIL, EmailSettings().model_dump(by_alias=True))
    repo.insert_if_missing(_SALT, {"value": secrets.token_hex(12)})
    repo.insert_if_missing(_SECRET, {"value": secrets.token_hex(32)})

    store_repo = StoreRepository(db)
    if store_repo.count() == 0:
        stores.create_store(db, "My Store")

    # Shared settings: seeded once from the first store (so an install that predates sharing keeps what it had).
    first = store_repo.list()[0]
    legacy_key = first.settings.get("apiKey")  # installs that predate the shared API key keep the first store's key
    seed = split_settings(StoreSettings.model_validate(first.settings))[1]
    repo.insert_if_missing(_SHARED, seed)
    current = repo.all()[_SHARED]
    if legacy_key and "apiKey" not in current:
        repo.set(_SHARED, {**current, "apiKey": legacy_key})

    # Settings introduced by newer versions (e.g. the client-API signing secret) are generated once and saved here,
    # instead of being re-generated every time the configuration is loaded.
    shared = repo.all()[_SHARED]
    complete_shared = split_settings(merged_settings({}, shared))[1]
    if complete_shared != shared:
        repo.set(_SHARED, complete_shared)
    for row in store_repo.list():
        complete = split_settings(StoreSettings.model_validate(row.settings))[0]
        if complete != row.settings:
            row.settings = complete


class ConfigService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached: AppConfig | None = None
        self._loaded_at = 0.0

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None

    def get(self, db: Session) -> AppConfig:
        with self._lock:
            if self._cached and time.monotonic() - self._loaded_at < _TTL_SECONDS:
                return self._cached
        rows = SettingsRepository(db).all()
        shared = rows.get(_SHARED, {})
        config = AppConfig(
            stores=tuple(_record(r, shared) for r in StoreRepository(db).list()),
            email=EmailSettings.model_validate(rows.get(_EMAIL, {})),
            salt=rows.get(_SALT, {}).get("value", ""),
            secret=rows.get(_SECRET, {}).get("value", ""),
        )
        with self._lock:
            self._cached, self._loaded_at = config, time.monotonic()
        return config

    def save_email(self, db: Session, email: EmailSettings) -> None:
        SettingsRepository(db).set(_EMAIL, email.model_dump(by_alias=True))
        self.invalidate()


config_service = ConfigService()
