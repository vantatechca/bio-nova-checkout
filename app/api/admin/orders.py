from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import Config, DbSession
from app.repositories import OrderRepository
from app.schemas.orders import OrderListOut, OrderOut, OrderUpdateIn
from app.services import orders

router = APIRouter(prefix="/api/admin/orders", tags=["admin: orders"])

MAX_ROWS = 500


@router.get("", response_model=OrderListOut)
def list_orders(
    db: DbSession,
    tab: Literal["pending", "paid", "failed"] | None = None,
    status: Literal["pending", "processing", "shipped", "completed", "cancelled", "refunded"] | None = None,
    q: str = Query(default="", max_length=100),
):
    rows, has_more = OrderRepository(db).list(tab=tab, status=status, search=q.strip(), limit=MAX_ROWS)
    return OrderListOut(data=rows, has_more=has_more)


@router.get("/{key}", response_model=OrderOut)
def get_order(key: str, db: DbSession):
    return orders.get_order(db, key)


@router.patch("/{key}", response_model=OrderOut)
def update_order(key: str, data: OrderUpdateIn, db: DbSession, config: Config):
    return orders.update_order(db, config, key, data)
