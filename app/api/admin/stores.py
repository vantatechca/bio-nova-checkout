from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Config, DbSession
from app.repositories import StoreRepository
from app.schemas.stores import StoreActiveIn, StoreCreateIn, StoreOut
from app.services import stores
from app.services.config import StoreRecord, config_service
from app.services.payments import card_available

router = APIRouter(prefix="/api/admin/stores", tags=["admin: stores"])


def _out(record: StoreRecord, orders: int) -> StoreOut:
    s = record.settings
    return StoreOut(
        id=record.id,
        slug=record.slug,
        name=record.name,
        active=record.active,
        logo_url=s.logo_url,
        store_url=s.store_url,
        shopify_domain=s.shopify_domain,
        card_ready=card_available(s),
        orders=orders,
    )


def _listing(db: DbSession) -> list[StoreOut]:
    config_service.invalidate()
    counts = StoreRepository(db).order_counts()
    return [_out(r, counts.get(r.id, 0)) for r in config_service.get(db).stores]


@router.get("", response_model=list[StoreOut])
def list_stores(db: DbSession, config: Config):
    counts = StoreRepository(db).order_counts()
    return [_out(r, counts.get(r.id, 0)) for r in config.stores]


@router.post("", response_model=StoreOut, status_code=201)
def create_store(data: StoreCreateIn, db: DbSession):
    row = stores.create_store(db, data.name, copy_from=data.copy_from)
    config_service.invalidate()
    record = next(r for r in config_service.get(db).stores if r.id == row.id)
    return _out(record, 0)


@router.patch("/{store_id}", response_model=StoreOut)
def set_active(store_id: int, data: StoreActiveIn, db: DbSession):
    stores.set_active(db, store_id, data.active)
    return next(s for s in _listing(db) if s.id == store_id)


@router.delete("/{store_id}", status_code=204)
def delete_store(store_id: int, db: DbSession) -> None:
    stores.delete_store(db, store_id)
