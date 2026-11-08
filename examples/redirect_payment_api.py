"""Reference implementation of the client's side of the redirect payment flow (see docs/redirect-payment.md).

Two parts:
  * POST /charge        receives our signed ``create_payment`` request and replies with the payment page URL.
  * mark_order_paid()   call this from your processor's "payment succeeded" webhook.

``create_payment_page`` is the only part to replace with the real processor call (for example a hosted checkout session).

    SIGNING_SECRET=capi_xxx uvicorn examples.redirect_payment_api:app --port 9000
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SIGNING_SECRET = os.environ.get("SIGNING_SECRET", "")
CHECKOUT_URL = os.environ.get("CHECKOUT_URL", "https://bio-nova-checkout.onrender.com")
CHECKOUT_API_KEY = os.environ.get("CHECKOUT_API_KEY", "")
MAX_CLOCK_SKEW_SECONDS = 300

app = FastAPI(title="Client redirect payment API (reference)")
_pages: dict[str, dict] = {}  # Idempotency-Key -> payment page already created. Use a database in production.


def verify(secret: str, timestamp: str, raw_body: bytes, signature: str) -> bool:
    try:
        if abs(time.time() - int(timestamp)) > MAX_CLOCK_SKEW_SECONDS:
            return False
    except ValueError:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_payment_page(payload: dict) -> dict:
    """REPLACE ME with the real processor call that creates a hosted payment page for this order.

    Use ``payload["amount"]`` (cents) and ``payload["currency"]``, and send the customer back to
    ``payload["return_url"]`` after payment (``payload["cancel_url"]`` on cancel).
    Return ``{"status": "redirect", "redirect_url": "https://...", "id": "<your payment id>"}``.
    """
    payment_id = f"pay_{hashlib.sha256(payload['reference'].encode()).hexdigest()[:12]}"
    return {"status": "redirect", "redirect_url": f"https://pay.example.com/p/{payment_id}", "id": payment_id}


@app.post("/charge")
async def charge(request: Request) -> JSONResponse:
    raw = await request.body()
    if not verify(
        SIGNING_SECRET,
        request.headers.get("x-checkout-timestamp", ""),
        raw,
        request.headers.get("x-checkout-signature", ""),
    ):
        return JSONResponse({"error": "bad signature"}, status_code=401)

    payload = await request.json()
    if payload.get("type") == "ping":  # sent by the admin's "Save & test client API" button
        return JSONResponse({"ok": True})

    key = request.headers.get("idempotency-key", "")
    if key not in _pages:  # the same Idempotency-Key must return the same payment page
        _pages[key] = create_payment_page(payload)
    return JSONResponse(_pages[key])


def mark_order_paid(reference: str, payment_id: str) -> dict:
    """Call from your processor's "payment succeeded" webhook. ``reference`` is the session id we sent you."""
    headers = {"Authorization": f"Bearer {CHECKOUT_API_KEY}"}
    with httpx.Client(base_url=CHECKOUT_URL, headers=headers, timeout=15) as client:
        session = client.get(f"/api/v1/checkout/sessions/{reference}")
        session.raise_for_status()
        order_id = session.json()["order_id"]
        order = client.patch(
            f"/api/v1/orders/{order_id}",
            json={"payment_status": "paid", "payment_reference": payment_id},
        )
        order.raise_for_status()
        return order.json()
