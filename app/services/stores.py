"""Managing the stores connected to this checkout."""

from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import BadRequest, NotFound
from app.models import Store
from app.models.types import utcnow
from app.repositories import StoreRepository
from app.schemas.settings import StoreSettings
from app.services.config import allowed_origins, config_service, mirror_columns


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "store"


def _unique_slug(repo: StoreRepository, base: str) -> str:
    slug, n = base, 2
    while repo.slug_exists(slug):
        suffix = f"-{n}"
        slug, n = base[: 60 - len(suffix)] + suffix, n + 1
    return slug


def create_store(db: Session, name: str, slug: str | None = None) -> Store:
    name = name.strip()
    if not name:
        raise BadRequest("Give the store a name")
    repo = StoreRepository(db)
    settings = StoreSettings(store_name=name[:100])
    row = Store(
        slug=_unique_slug(repo, slugify(slug or name)),
        name=settings.store_name,
        active=True,
        api_key=settings.api_key,
        shopify_domain=None,
        settings=settings.model_dump(by_alias=True),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    repo.add(row)
    config_service.invalidate()
    return row


def _require(repo: StoreRepository, store_id: int) -> Store:
    row = repo.get(store_id)
    if row is None:
        raise NotFound("Store not found")
    return row


def save_settings(db: Session, store_id: int, settings: StoreSettings) -> Store:
    repo = StoreRepository(db)
    row = _require(repo, store_id)
    mine = allowed_origins(settings)
    for other in repo.list():
        if other.id == store_id or not mine:
            continue
        if mine & allowed_origins(StoreSettings.model_validate(other.settings)):
            raise BadRequest(
                f"The website or Shopify domain overlaps with the store “{other.name}”. Each store needs its own."
            )
    try:
        mirror_columns(row, settings)
        row.updated_at = utcnow()
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BadRequest("That API key or Shopify domain is already used by another store") from exc
    config_service.invalidate()
    return row


def set_active(db: Session, store_id: int, active: bool) -> Store:
    repo = StoreRepository(db)
    row = _require(repo, store_id)
    if not active and sum(1 for s in repo.list() if s.active and s.id != store_id) == 0:
        raise BadRequest("At least one store has to stay active")
    row.active = active
    row.updated_at = utcnow()
    config_service.invalidate()
    return row


def delete_store(db: Session, store_id: int) -> None:
    repo = StoreRepository(db)
    row = _require(repo, store_id)
    if repo.count() <= 1:
        raise BadRequest("You can't delete the only store")
    if repo.has_activity(store_id):
        raise BadRequest("This store has orders or checkouts, so it can't be deleted. Deactivate it instead.")
    repo.delete(row)
    config_service.invalidate()
