"""Order management used by both the admin UI and the store API."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import Order, OrderStatus, PaymentStatus
from app.models.types import utcnow
from app.repositories import OrderRepository
from app.schemas.orders import OrderUpdateIn
from app.services import notifications
from app.services.config import AppConfig
from app.services.notifications import OrderChange


def get_order(db: Session, key: str, store_id: int | None = None) -> Order:
    order = OrderRepository(db, store_id).get(key)
    if order is None:
        raise NotFound("Order not found")
    return order


def apply_update(order: Order, data: OrderUpdateIn) -> OrderChange:
    """Mutates ``order`` (which must be row-locked) and records every change in its history."""
    changes: list[str] = []
    change = OrderChange()

    if data.status is not None and data.status != order.status:
        changes.append(f"Status: {order.status} → {data.status}")
        change.became_shipped = data.status == OrderStatus.SHIPPED
        change.became_cancelled = data.status == OrderStatus.CANCELLED
        order.status = data.status

    if data.payment_status is not None and data.payment_status != order.payment_status:
        changes.append(f"Payment: {order.payment_status} → {data.payment_status}")
        if data.payment_status == PaymentStatus.PAID:
            change.became_paid = True
            order.paid_at = utcnow()
            # Marking a still-pending order as paid moves it on to processing (unless a status was also given).
            if order.status == OrderStatus.PENDING and data.status is None:
                order.status = OrderStatus.PROCESSING
                changes.append(f"Status: {OrderStatus.PENDING} → {OrderStatus.PROCESSING}")
        order.payment_status = data.payment_status

    if data.payment_reference is not None and data.payment_reference != order.payment_reference:
        order.payment_reference = data.payment_reference
        changes.append(f"Payment reference: {data.payment_reference or 'cleared'}")

    if data.notes is not None and data.notes.strip() != order.notes:
        order.notes = data.notes.strip()
        changes.append("Notes updated")

    if data.tracking_number is not None and data.tracking_number != order.tracking_number:
        order.tracking_number = data.tracking_number
        changes.append(f"Tracking: {data.tracking_number or 'cleared'}")

    if changes:
        now = utcnow()
        order.updated_at = now
        for text in changes:
            order.add_event(text, now)
        change.changed = True
    return change


def update_order(db: Session, config: AppConfig, key: str, data: OrderUpdateIn, store_id: int | None = None) -> Order:
    """Row-locks the order, applies the update and queues notifications, all in one transaction."""
    order = OrderRepository(db, store_id).get_for_update(key)
    if order is None:
        raise NotFound("Order not found")
    change = apply_update(order, data)
    notifications.order_updated(db, config, order, change, notify_customer=data.notify)
    return order
