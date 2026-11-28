"""Order management used by both the admin UI and the store API."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.database import session_scope
from app.errors import NotFound
from app.models import Order, OrderStatus, PaymentAttempt, PaymentStatus
from app.models.types import utcnow
from app.repositories import OrderRepository, PaymentAttemptRepository
from app.schemas.analytics import AnalyticsOrderListOut, AnalyticsOrderListRow
from app.schemas.orders import OrderUpdateIn
from app.services import notifications, reports
from app.services.config import AppConfig, config_service
from app.services.notifications import OrderChange

log = logging.getLogger(__name__)

# A redirect-flow payment page is normally paid or abandoned within minutes; 24h stuck pending with no word
# from the payment partner is treated as "this isn't coming," not "still in progress."
STALE_PENDING_PAYMENT_HOURS = 24


def get_order(db: Session, key: str, store_id: int | None = None) -> Order:
    order = OrderRepository(db, store_id).get(key)
    if order is None:
        raise NotFound("Order not found")
    return order


def mask_email(email: str) -> str:
    """``j***@example.com`` -- the first character of the local part plus the whole domain (so a repeat
    customer, or which provider they used, is still recognisable), the rest of the local part masked."""
    if not email or "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}{'*' * max(len(local) - 1, 2)}@{domain}"


def mask_phone(phone: str) -> str:
    """Keeps only the last 4 digits visible (fewer for anything shorter than that, never the whole thing)."""
    if not phone:
        return ""
    visible = 4 if len(phone) > 5 else max(len(phone) - 2, 0)
    masked = len(phone) - visible
    return "*" * masked + phone[masked:]


def analytics_orders(
    db: Session,
    store_id: int | None,
    days: int,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    offset: int,
) -> AnalyticsOrderListOut:
    """Read-only orders feed for the analytics key (see app.api.analytics): customer contact info is masked,
    never omitted outright or returned raw -- enough to recognise a repeat customer, not enough to contact them."""
    window = reports.resolve_window(days, 0, date_from, date_to)
    rows, has_more = OrderRepository(db, store_id).analytics_list(window.since, window.until, limit, offset)
    return AnalyticsOrderListOut(
        rows=[
            AnalyticsOrderListRow(
                number=o.number,
                store_id=o.store_id,
                created_at=o.created_at,
                status=o.status,
                payment_status=o.payment_status,
                total=o.total,
                currency=o.currency,
                utm_source=o.utm_source,
                utm_medium=o.utm_medium,
                utm_campaign=o.utm_campaign,
                utm_content=o.utm_content,
                utm_term=o.utm_term,
                click_provider=o.click_provider,
                click_id=o.click_id,
                customer_email_masked=mask_email(o.customer_email),
                customer_phone_masked=mask_phone(o.customer_phone),
            )
            for o in rows
        ],
        has_more=has_more,
    )


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
        elif data.payment_status == PaymentStatus.FAILED:
            change.became_failed = True
        # A fresh clock each time an order (re-)enters pending (e.g. reset for a retry); cleared once it leaves
        # pending, so a paid/failed/refunded order is never a candidate for the stale-payment expiry sweep.
        order.pending_since = utcnow() if data.payment_status == PaymentStatus.PENDING else None
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
    if change.became_failed:
        attempts = PaymentAttemptRepository(db)
        attempts.add(
            PaymentAttempt(
                store_id=order.store_id,
                session_id=order.session_id,
                outcome="declined",
                method_id=order.payment_method_id,
                attempt_no=attempts.count_for(order.session_id) + 1,
            )
        )
    notifications.order_updated(db, config, order, change, notify_customer=data.notify)
    return order


def expire_stale_pending_payments() -> int:
    """Marks failed any redirect-flow order (a payment_url was issued) that's been pending for more than
    ``STALE_PENDING_PAYMENT_HOURS`` with no confirmation from the payment partner -- X8: "a look at why 2 pay
    clicks produced no order" led here, and to a signed/idempotent partner webhook that already existed (see
    docs/redirect-payment.md step 4), but nothing was handling the case where that webhook simply never comes.

    Orders are never deleted: this only changes payment_status, same as any other decline, with its own history
    line. Offline/bank-transfer orders (no payment_url) are never touched -- sitting pending is their normal,
    expected state, not a stuck payment.

    Each candidate is row-locked and re-checked in its own short transaction, separately from the read that found
    it (same pattern as app.workers.outbox): a payment confirmation that lands in the same instant always wins
    over this sweep, never the other way around. Called from app.workers.outbox alongside the other periodic
    maintenance, but kept here rather than in app.services.maintenance -- this is order/payment lifecycle logic,
    the same domain as apply_update/update_order above, not generic data retention.
    """
    cutoff = utcnow() - timedelta(hours=STALE_PENDING_PAYMENT_HOURS)
    with session_scope() as db:
        candidate_ids = [o.public_id for o in OrderRepository(db).stale_pending_redirect_payments(cutoff)]

    expired = 0
    for public_id in candidate_ids:
        with session_scope() as db:
            order = OrderRepository(db).get_for_update(public_id)
            if order is None or order.payment_status != PaymentStatus.PENDING or not order.payment_url:
                continue  # already resolved (e.g. the partner's webhook landed first) -- nothing to do
            now = utcnow()
            order.payment_status = PaymentStatus.FAILED
            order.pending_since = None
            order.updated_at = now
            order.add_event(f"Automatically marked failed: no payment confirmation within {STALE_PENDING_PAYMENT_HOURS}h", now)
            attempts = PaymentAttemptRepository(db)
            attempts.add(
                PaymentAttempt(
                    store_id=order.store_id,
                    session_id=order.session_id,
                    outcome="declined",
                    method_id=order.payment_method_id,
                    attempt_no=attempts.count_for(order.session_id) + 1,
                )
            )
            notifications.order_updated(db, config_service.get(db), order, OrderChange(became_failed=True), notify_customer=True)
            expired += 1
    if expired:
        log.info("Marked %d stale pending redirect-flow orders as failed", expired)
    return expired
