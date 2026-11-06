"""Turns domain events into outbox rows (emails + webhooks) inside the caller's transaction."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Order, PaymentStatus
from app.services.config import AppConfig
from app.services.emails import queue_email
from app.services.webhooks import enqueue_webhook


@dataclass
class OrderChange:
    """What an update actually changed; drives which notifications fire."""

    changed: bool = False
    became_paid: bool = False
    became_shipped: bool = False
    became_cancelled: bool = False


def order_created(db: Session, config: AppConfig, order: Order) -> None:
    enqueue_webhook(db, config, "order.created", order)
    if order.payment_status == PaymentStatus.PAID:
        enqueue_webhook(db, config, "order.paid", order)
    queue_email(db, config, "confirmation", order)
    queue_email(db, config, "admin", order)


def order_updated(db: Session, config: AppConfig, order: Order, change: OrderChange, *, notify_customer: bool) -> None:
    if not change.changed:
        return
    enqueue_webhook(db, config, "order.updated", order)
    if change.became_paid:
        enqueue_webhook(db, config, "order.paid", order)
    if not notify_customer:
        return
    if change.became_paid:
        queue_email(db, config, "paid", order)
    if change.became_shipped:
        queue_email(db, config, "shipped", order)
    if change.became_cancelled:
        queue_email(db, config, "cancelled", order)
