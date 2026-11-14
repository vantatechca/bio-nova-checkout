"""Checkout sessions: creation by the store and completion (order placement) by the customer."""

from __future__ import annotations

import re
import secrets
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import BadRequest, Gone, NotFound
from app.models import CheckoutSession, Order, OrderItem, OrderStatus, PaymentStatus, SessionStatus
from app.models.types import utcnow
from app.repositories import OrderRepository, SessionRepository
from app.schemas.checkout import (
    Branding,
    CardPublic,
    CompleteSessionIn,
    CreateSessionIn,
    PaymentMethodPublic,
    PublicSessionOut,
    SessionOut,
)
from app.schemas.settings import StoreSettings
from app.services import notifications
from app.services.config import AppConfig, StoreRecord
from app.services.money import format_money
from app.services.payments import PaymentRequest, card_available, process_payment

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def fill_template(template: str, **values: object) -> str:
    """Substitutes ``{order}`` / ``{total}`` / ``{store}`` placeholders; unknown ones are left as written."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template)


def check_redirect_url(url: str, field: str, store: StoreSettings, *, required: bool = False) -> str:
    if not url:
        if required:
            raise BadRequest(f"{field} is required")
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BadRequest(f"{field} must be a valid http(s) URL")
    allowed = store.allowed_domain_list
    host = parsed.hostname.lower()
    if allowed and not any(host == d or host.endswith("." + d) for d in allowed):
        raise BadRequest(f"{field} host is not in the allowed domains list")
    return url


# ---------------------------------------------------------------- store side
def store_for(config: AppConfig, store_id: int) -> StoreRecord:
    store = config.store_by_id(store_id)
    if store is None:
        raise NotFound("Store not found")
    return store


def create_session(db: Session, store_record: StoreRecord, data: CreateSessionIn) -> CheckoutSession:
    store = store_record.settings
    currency = (data.currency or store.currency).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise BadRequest("currency must be a 3-letter code")

    items = [item.model_dump() for item in data.items]
    subtotal = sum(i["unit_amount"] * i["quantity"] for i in items)
    if data.shipping_amount is not None:
        shipping = data.shipping_amount
    elif store.free_shipping_min and subtotal >= store.free_shipping_min:
        shipping = 0  # the free-shipping promotion is unlocked
    else:
        shipping = store.shipping_flat
    tax = data.tax_amount if data.tax_amount is not None else round(subtotal * store.tax_rate_percent / 100)

    session = CheckoutSession(
        id=f"cs_{secrets.token_hex(16)}",
        store_id=store_record.id,
        status=SessionStatus.OPEN,
        currency=currency,
        items=items,
        subtotal=subtotal,
        shipping=shipping,
        tax=tax,
        total=subtotal + shipping + tax,
        customer_name=data.customer.name,
        customer_email=data.customer.email,
        customer_phone=data.customer.phone,
        success_url=check_redirect_url(data.success_url, "success_url", store, required=True),
        cancel_url=check_redirect_url(data.cancel_url, "cancel_url", store),
        external_ref=data.external_ref,
        meta=data.metadata,
        expires_at=utcnow() + timedelta(hours=get_settings().session_ttl_hours),
    )
    SessionRepository(db).add(session)
    return session


def get_session(db: Session, session_id: str, store_id: int | None = None) -> CheckoutSession:
    """Fetches a session; with ``store_id`` a store can only see its own."""
    session = SessionRepository(db).get(session_id)
    if session is None or (store_id is not None and session.store_id != store_id):
        raise NotFound("Session not found")
    if session.status == SessionStatus.OPEN and session.is_expired:
        session.status = SessionStatus.EXPIRED
    return session


def session_out(session: CheckoutSession, base_url: str) -> SessionOut:
    out = SessionOut.model_validate(session)
    out.checkout_url = f"{base_url.rstrip('/')}/checkout?session={session.id}"
    return out


# ---------------------------------------------------------------- customer side
def build_success_url(session: CheckoutSession, order: Order) -> str:
    parts = urlparse(session.success_url)
    query = dict(parse_qsl(parts.query))
    query.update({"checkout_session": session.id, "order": str(order.number)})
    if session.external_ref:
        query["ref"] = session.external_ref
    return urlunparse(parts._replace(query=urlencode(query)))


def public_view(config: AppConfig, session: CheckoutSession, order: Order | None) -> PublicSessionOut:
    store = store_for(config, session.store_id).settings
    card_ready = card_available(store)
    methods = [
        PaymentMethodPublic(
            id=m.id,
            label=m.label,
            type=m.type,
            instructions=fill_template(
                m.instructions,
                order="your order number",
                total=format_money(session.total, session.currency),
                store=store.store_name,
            ),
        )
        for m in store.payment_methods
        if m.enabled and (m.type != "card" or card_ready)  # card needs its processor configured
    ]
    card = (
        CardPublic(provider=store.card_provider, public_key=store.card_public_key, form_url=store.card_form_url)
        if card_ready
        else None
    )
    return PublicSessionOut(
        id=session.id,
        status=session.status,
        store_name=store.store_name,
        currency=session.currency,
        items=session.items,
        subtotal=session.subtotal,
        shipping=session.shipping,
        free_shipping_min=store.free_shipping_min,
        tax=session.tax,
        total=session.total,
        customer=session.customer,
        cancel_url=session.cancel_url,
        success_url=build_success_url(session, order) if order and session.status == SessionStatus.COMPLETE else None,
        order_number=order.number if order else None,
        payment_instructions=order.payment_instructions if order else None,
        payment_status=order.payment_status if order else None,
        payment_url=(order.payment_url or "") if order and order.payment_status == PaymentStatus.PENDING else "",
        payment_methods=methods,
        card=card,
        branding=Branding(
            logo_url=store.logo_url,
            store_url=store.store_url,
            nav_links=[{"label": link.label, "url": link.url} for link in store.nav_links],
            notice=store.notice,
        ),
    )


REDIRECT_PENDING = (
    "We're waiting for your payment to be confirmed. If you didn't finish paying, please use the chat on our store."
)


def complete_session(
    db: Session, config: AppConfig, session_id: str, data: CompleteSessionIn, base_url: str = ""
) -> tuple[CheckoutSession, Order, str]:
    """Places the order for a session. Returns ``(session, order, redirect_url)``.

    ``redirect_url`` is only set when the customer must go on to the client's payment page (redirect card flow).

    The session row is locked for the duration of the transaction, so double-clicks and
    retries can never create two orders: later callers just receive the existing one.
    """
    sessions, orders = SessionRepository(db), OrderRepository(db)
    session = sessions.get_for_update(session_id)
    if session is None:
        raise NotFound("Session not found")
    if session.status == SessionStatus.COMPLETE and session.order_id:
        order = orders.get(session.order_id)
        # Back from the payment page and pressing Pay again: send them to the same payment page.
        resume = order.payment_url if order.payment_status == PaymentStatus.PENDING else ""
        return session, order, resume or ""  # idempotent
    if session.is_expired:
        raise Gone("This checkout session has expired")

    customer, address = data.customer, data.shipping_address
    if not customer.name:
        raise BadRequest("Name is required")
    if not EMAIL_RE.fullmatch(customer.email):
        raise BadRequest("A valid email is required")
    if not (address.line1 and address.city and address.postal_code and address.country):
        raise BadRequest("Please complete the shipping address")
    store = store_for(config, session.store_id).settings
    method = next((m for m in store.payment_methods if m.enabled and m.id == data.payment_method), None)
    if method is None:
        raise BadRequest("Please choose a payment method")

    # For card payments this charges the card (via the client's API) while the session row is locked, so a
    # double-click can never charge twice. A decline raises BadRequest and no order is created.
    payment = process_payment(
        method,
        session,
        PaymentRequest(
            store=store,
            customer=customer,
            address=address,
            token=data.card_token,
            return_url=f"{base_url.rstrip('/')}/checkout?session={session.id}",
        ),
    )
    payment_status = payment.status
    now = utcnow()
    order = Order(
        store_id=session.store_id,
        public_id=f"ord_{secrets.token_hex(8)}",
        session_id=session.id,
        external_ref=session.external_ref,
        status=OrderStatus.PROCESSING if payment_status == PaymentStatus.PAID else OrderStatus.PENDING,
        payment_status=payment_status,
        payment_method_id=method.id,
        payment_method_label=method.label,
        payment_reference=payment.reference,
        payment_url=payment.redirect_url or None,
        currency=session.currency,
        subtotal=session.subtotal,
        shipping=session.shipping,
        tax=session.tax,
        total=session.total,
        customer_name=customer.name,
        customer_email=customer.email,
        customer_phone=customer.phone,
        ship_line1=address.line1,
        ship_line2=address.line2,
        ship_city=address.city,
        ship_state=address.state,
        ship_postal_code=address.postal_code,
        ship_country=address.country,
        meta=session.meta,
        paid_at=now if payment_status == PaymentStatus.PAID else None,
        created_at=now,
        updated_at=now,
        items=[
            OrderItem(
                position=i,
                name=it["name"],
                sku=it.get("sku", ""),
                description=it.get("description", ""),
                image=it.get("image", ""),
                unit_amount=it["unit_amount"],
                quantity=it["quantity"],
            )
            for i, it in enumerate(session.items)
        ],
    )
    order.add_event(f"Order placed ({method.label})", now)
    if payment.redirect_url:
        order.add_event(
            "Customer sent to the payment page" + (f" (ref {payment.reference})" if payment.reference else ""), now
        )
    elif payment.reference:
        order.add_event(f"Payment received (ref {payment.reference})", now)
    orders.add(order)  # flush assigns order.number
    order.payment_instructions = (
        REDIRECT_PENDING
        if payment.redirect_url
        else fill_template(
            method.instructions,
            order=order.number,
            total=format_money(order.total, order.currency),
            store=store.store_name,
        )
    )
    session.status, session.order_id = SessionStatus.COMPLETE, order.public_id
    notifications.order_created(db, config, order)
    return session, order, payment.redirect_url
