from __future__ import annotations

import csv
import io
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import Config, DbSession, StoreScope
from app.repositories import OrderRepository
from app.schemas.orders import OrderListOut, OrderOut, OrderUpdateIn
from app.services import orders

router = APIRouter(prefix="/api/admin/orders", tags=["admin: orders"])

MAX_ROWS = 500
EXPORT_ROWS = 10000
EXPORT_COLUMNS = (
    "number",
    "created_at",
    "paid_at",
    "status",
    "payment_status",
    "total",
    "currency",
    "email",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "click_provider",
    "click_id",
)


@router.get("", response_model=OrderListOut)
def list_orders(
    db: DbSession,
    store: StoreScope,
    tab: Literal["pending", "paid", "failed"] | None = None,
    status: Literal["pending", "processing", "shipped", "completed", "cancelled", "refunded"] | None = None,
    q: str = Query(default="", max_length=100),
):
    rows, has_more = OrderRepository(db, store).list(tab=tab, status=status, search=q.strip(), limit=MAX_ROWS)
    return OrderListOut(data=rows, has_more=has_more)


@router.get("/export")
def export_orders(db: DbSession, store: StoreScope) -> Response:
    """A CSV of orders (current store filter), including attribution, for spreadsheets / ad platforms."""
    rows, _ = OrderRepository(db, store).list(limit=EXPORT_ROWS)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for o in rows:
        writer.writerow(
            [
                o.number,
                o.created_at.isoformat(),
                o.paid_at.isoformat() if o.paid_at else "",
                o.status,
                o.payment_status,
                o.total,
                o.currency,
                o.customer_email,
                o.utm_source,
                o.utm_medium,
                o.utm_campaign,
                o.click_provider,
                o.click_id,
            ]
        )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders.csv"},
    )


@router.get("/{key}", response_model=OrderOut)
def get_order(key: str, db: DbSession, store: StoreScope):
    return orders.get_order(db, key, store)


@router.patch("/{key}", response_model=OrderOut)
def update_order(key: str, data: OrderUpdateIn, db: DbSession, config: Config, store: StoreScope):
    return orders.update_order(db, config, key, data, store)
