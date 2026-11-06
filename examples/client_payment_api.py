"""Reference implementation of the *client's* charge endpoint (see docs/client-payment-api.md).

This is what the merchant's developers build on their own server. It verifies our signed request, is idempotent, and
calls the processor to charge the token. ``charge_with_processor`` is the only part to replace with the real processor
SDK call; as shipped it simulates one so the whole flow can be tried end to end.

    SIGNING_SECRET=capi_xxx uvicorn examples.client_payment_api:app --port 9000
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SIGNING_SECRET = os.environ.get("SIGNING_SECRET", "")
MAX_CLOCK_SKEW_SECONDS = 300

app = FastAPI(title="Client payment API (reference)")
_lock = threading.Lock()
# Idempotency-Key -> the *successful* charge we already made. Use a database in production.
# Only successes are remembered: a declined card must not block the customer from trying another card.
_successes: dict[str, dict] = {}


def verify(secret: str, timestamp: str, raw_body: bytes, signature: str) -> bool:
    """Checks the request really came from the checkout (shared secret) and isn't a replay."""
    try:
        if abs(time.time() - int(timestamp)) > MAX_CLOCK_SKEW_SECONDS:
            return False
    except ValueError:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def charge_with_processor(token: str, amount: int, currency: str, description: str) -> dict:
    """REPLACE ME with the real processor call, e.g. Stripe: ``stripe.PaymentIntent.create(amount=amount,
    currency=currency.lower(), payment_method=token, confirm=True, description=description, ...)``.

    Return ``{"status": "succeeded", "id": "<charge id>"}`` or ``{"status": "declined", "message": "..."}``.
    """
    if token.endswith("0002"):  # simulated decline (the test provider's "4000 0000 0000 0002" card)
        return {"status": "declined", "message": "Your card has insufficient funds."}
    return {"status": "succeeded", "id": f"ch_{hashlib.sha256(token.encode()).hexdigest()[:14]}"}


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
    if payload.get("type") == "ping":
        return JSONResponse({"ok": True})

    key = request.headers.get("idempotency-key", "")
    with _lock:  # one charge per Idempotency-Key, even if two identical requests arrive at once
        if key and key in _successes:  # this payment already went through: answer again, never charge twice
            return JSONResponse(_successes[key])
        result = charge_with_processor(
            token=payload["token"],
            amount=int(payload["amount"]),
            currency=payload["currency"],
            description=payload.get("description", ""),
        )
        if key and result.get("status") == "succeeded":
            _successes[key] = result
        return JSONResponse(result)
