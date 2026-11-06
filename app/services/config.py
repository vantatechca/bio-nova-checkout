"""Runtime configuration stored in the database, with a short-lived in-process cache."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import SettingsRepository
from app.schemas.settings import EmailSettings, StoreSettings

_STORE, _EMAIL, _SALT, _SECRET = "store", "email", "salt", "secret"
_TTL_SECONDS = 5.0  # other app instances' edits become visible within this window


@dataclass(frozen=True)
class AppConfig:
    store: StoreSettings
    email: EmailSettings
    salt: str  # salts the visitor hash (privacy-preserving unique-visitor counts)
    secret: str  # signs admin tokens


def ensure_defaults(db: Session) -> None:
    """First-run seeding. Existing rows are never overwritten."""
    repo = SettingsRepository(db)
    repo.insert_if_missing(_STORE, StoreSettings().model_dump(by_alias=True))
    repo.insert_if_missing(_EMAIL, EmailSettings().model_dump(by_alias=True))
    repo.insert_if_missing(_SALT, {"value": secrets.token_hex(12)})
    repo.insert_if_missing(_SECRET, {"value": secrets.token_hex(32)})

    # Settings introduced by newer versions (e.g. the client-API signing secret) are generated once and saved here,
    # instead of being re-generated every time the configuration is loaded.
    stored = repo.all().get(_STORE, {})
    complete = StoreSettings.model_validate(stored).model_dump(by_alias=True)
    if complete != stored:
        repo.set(_STORE, complete)


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
        config = AppConfig(
            store=StoreSettings.model_validate(rows.get(_STORE, {})),
            email=EmailSettings.model_validate(rows.get(_EMAIL, {})),
            salt=rows.get(_SALT, {}).get("value", ""),
            secret=rows.get(_SECRET, {}).get("value", ""),
        )
        with self._lock:
            self._cached, self._loaded_at = config, time.monotonic()
        return config

    def save_store(self, db: Session, store: StoreSettings) -> None:
        SettingsRepository(db).set(_STORE, store.model_dump(by_alias=True))
        self.invalidate()

    def save_email(self, db: Session, email: EmailSettings) -> None:
        SettingsRepository(db).set(_EMAIL, email.model_dump(by_alias=True))
        self.invalidate()


config_service = ConfigService()
