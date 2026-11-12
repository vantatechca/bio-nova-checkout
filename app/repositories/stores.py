from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CheckoutSession, Order, Store


class StoreRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[Store]:
        return list(self.db.scalars(select(Store).order_by(Store.id)))

    def get(self, store_id: int) -> Store | None:
        return self.db.get(Store, store_id)

    def get_for_update(self, store_id: int) -> Store | None:
        return self.db.scalars(select(Store).where(Store.id == store_id).with_for_update()).first()

    def slug_exists(self, slug: str) -> bool:
        return self.db.scalar(select(Store.id).where(Store.slug == slug)) is not None

    def count(self) -> int:
        return int(self.db.scalar(select(func.count(Store.id))) or 0)

    def add(self, store: Store) -> None:
        self.db.add(store)
        self.db.flush()

    def delete(self, store: Store) -> None:
        self.db.delete(store)
        self.db.flush()

    def order_counts(self) -> dict[int, int]:
        rows = self.db.execute(select(Order.store_id, func.count()).group_by(Order.store_id)).all()
        return {int(sid): int(n) for sid, n in rows}

    def has_activity(self, store_id: int) -> bool:
        """True when the store owns orders or checkout sessions (it can then no longer be deleted)."""
        return (
            self.db.scalar(select(Order.number).where(Order.store_id == store_id).limit(1)) is not None
            or self.db.scalar(select(CheckoutSession.id).where(CheckoutSession.store_id == store_id).limit(1))
            is not None
        )
