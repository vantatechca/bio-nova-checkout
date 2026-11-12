"""Admin-side editing of store and email settings."""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.schemas.settings import (
    EmailSettings,
    EmailSettingsUpdate,
    StoreSettings,
    StoreSettingsUpdate,
    new_secret,
)
from app.services import stores
from app.services.config import AppConfig, StoreRecord, config_service


def update_store(db: Session, record: StoreRecord, update: StoreSettingsUpdate) -> StoreSettings:
    changes = update.model_dump(exclude_unset=True)
    store = record.settings.model_copy(
        update={k: v for k, v in changes.items() if k != "payment_methods" and v is not None}
    )
    if update.payment_methods is not None:
        methods = []
        for method in update.payment_methods:
            method = method.model_copy()
            method.id = method.id or f"pm_{secrets.token_hex(2)}"
            method.label = method.label or method.id
            methods.append(method)
        store = store.model_copy(update={"payment_methods": methods})
    store = StoreSettings.model_validate(store.model_dump())  # re-run validators on the merged result
    stores.save_settings(db, record.id, store)
    return store


def rotate_api_key(db: Session, record: StoreRecord) -> str:
    store = record.settings.model_copy(update={"api_key": new_secret("sk")})
    stores.save_settings(db, record.id, store)
    return store.api_key


def rotate_webhook_secret(db: Session, record: StoreRecord) -> str:
    store = record.settings.model_copy(update={"webhook_secret": new_secret("whsec")})
    stores.save_settings(db, record.id, store)
    return store.webhook_secret


def update_email(db: Session, config: AppConfig, update: EmailSettingsUpdate) -> EmailSettings:
    email = config.email.model_copy(deep=True)
    if update.admin_email is not None:
        email.admin_email = update.admin_email
    if update.notify is not None:
        for name, value in update.notify.model_dump(exclude_none=True).items():
            setattr(email.notify, name, value)
    if update.smtp is not None:
        smtp, patch = email.smtp, update.smtp
        for name in ("host", "port", "secure", "user", "from_address"):
            value = getattr(patch, name)
            if value is not None:
                setattr(smtp, name, value)
        if patch.password:  # blank keeps the saved password
            smtp.password = patch.password
        if patch.clear_pass:
            smtp.password = ""
    config_service.save_email(db, email)
    return email


def masked_email_settings(email: EmailSettings) -> dict:
    """Email settings safe to send to the browser: the SMTP password is never returned."""
    data = email.model_dump(by_alias=True)
    data["smtp"]["passSet"] = bool(email.smtp.password)
    data["smtp"]["pass"] = ""
    return data
