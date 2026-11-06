"""Outgoing signed webhooks with persistent retry."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app.models import DeliveryState, Order, WebhookDelivery
from app.models.types import utcnow
from app.repositories import OutboxRepository
from app.schemas.orders import OrderOut
from app.services.config import AppConfig

TIMEOUT_SECONDS = 8
RETRY_DELAYS = (timedelta(seconds=30), timedelta(minutes=5), timedelta(minutes=30))  # => up to 4 attempts


def sign(secret: str, payload: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def enqueue_webhook(db: Session, config: AppConfig, event: str, order: Order) -> WebhookDelivery | None:
    """Freezes the payload and signature now so every retry is byte-identical (receivers can de-duplicate on ``id``)."""
    if not config.store.webhook_url:
        return None
    now = utcnow()
    payload = json.dumps(
        {
            "id": f"evt_{secrets.token_hex(8)}",
            "event": event,
            "created": now.isoformat().replace("+00:00", "Z"),
            "data": OrderOut.model_validate(order).model_dump(mode="json"),
        },
        separators=(",", ":"),
    )
    delivery = WebhookDelivery(
        id=f"wh_{secrets.token_hex(8)}",
        event=event,
        order_number=order.number,
        url=config.store.webhook_url,
        payload=payload,
        signature=sign(config.store.webhook_secret, payload),
        next_attempt_at=now,
    )
    OutboxRepository(db).add_webhook(delivery)
    return delivery


def attempt_delivery(delivery: WebhookDelivery) -> None:
    """One HTTP attempt; records the outcome and schedules a retry on the row (the caller commits)."""
    delivery.attempts += 1
    try:
        response = httpx.post(
            delivery.url,
            content=delivery.payload,
            headers={
                "Content-Type": "application/json",
                "X-Checkout-Event": delivery.event,
                "X-Checkout-Signature": delivery.signature,
            },
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        delivery.http_status, delivery.error = response.status_code, None
        delivered = 200 <= response.status_code < 300
    except httpx.HTTPError as exc:
        delivery.http_status, delivery.error = None, (str(exc) or type(exc).__name__)[:500]
        delivered = False

    if delivered:
        delivery.state, delivery.next_attempt_at = DeliveryState.DELIVERED, None
    elif delivery.attempts <= len(RETRY_DELAYS):
        delivery.state = DeliveryState.PENDING
        delivery.next_attempt_at = utcnow() + RETRY_DELAYS[delivery.attempts - 1]
    else:
        delivery.state, delivery.next_attempt_at = DeliveryState.FAILED, None
