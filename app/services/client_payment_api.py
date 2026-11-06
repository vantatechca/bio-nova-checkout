"""Client of the *client's* payment API: how this checkout asks their backend to charge a card token.

The card number never reaches this server. The checkout page puts it into the processor's own fields, gets a
single-use token back, and we pass that token to the client's endpoint, which charges it with their processor
account. The wire contract (signing, idempotency, responses) is documented in docs/client-payment-api.md.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.errors import BadGateway, BadRequest
from app.schemas.settings import StoreSettings

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20
UNAVAILABLE = "Card payments are temporarily unavailable. Please try another payment method."
UNCONFIRMED = "We couldn't confirm your payment. Please try again — your card won't be charged twice."
UNREACHED = "We couldn't reach the payment service, so you have not been charged. Please try again."
DECLINED = "Your card was declined. Please try another card."


@dataclass(frozen=True)
class ChargeResult:
    reference: str  # the processor's charge id, stored on the order


def sign(secret: str, timestamp: str, body: str) -> str:
    """``sha256=`` + hex HMAC-SHA256 of ``"<timestamp>.<raw body>"``. The client recomputes this to authenticate us."""
    mac = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"sha256={mac}"


class _Unreachable(Exception):
    """The request never got an answer (connection refused / timed out)."""

    def __init__(self, certain_not_charged: bool, detail: str) -> None:
        super().__init__(detail)
        self.certain_not_charged, self.detail = certain_not_charged, detail


def _post(store: StoreSettings, payload: dict, idempotency_key: str) -> httpx.Response:
    body = json.dumps(payload, separators=(",", ":"))
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-Checkout-Timestamp": timestamp,
        "X-Checkout-Signature": sign(store.client_api_secret, timestamp, body),
        "Idempotency-Key": idempotency_key,
    }
    try:
        return httpx.post(
            store.client_api_url, content=body, headers=headers, timeout=TIMEOUT_SECONDS, follow_redirects=False
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:  # nothing was sent, so nothing can have been charged
        raise _Unreachable(True, str(exc) or type(exc).__name__) from exc
    except httpx.HTTPError as exc:  # may have been sent: outcome unknown (the idempotency key makes a retry safe)
        raise _Unreachable(False, str(exc) or type(exc).__name__) from exc


def _exchange(store: StoreSettings, payload: dict, idempotency_key: str) -> dict:
    """Sends one signed request and returns the parsed JSON reply, or raises ``BadGateway`` with a customer-safe message."""
    try:
        response = _post(store, payload, idempotency_key)
    except _Unreachable as exc:
        log.warning("Client payment API unreachable: %s", exc.detail)
        raise BadGateway(UNREACHED if exc.certain_not_charged else UNCONFIRMED) from exc

    if response.status_code in (401, 403):
        log.error("Client payment API rejected our signature (HTTP %s): check the signing secret", response.status_code)
        raise BadGateway(UNAVAILABLE)
    if response.status_code >= 500:
        log.warning("Client payment API error: HTTP %s", response.status_code)
        raise BadGateway(UNCONFIRMED)
    try:
        body = response.json()
    except ValueError as exc:
        log.warning("Client payment API sent an unreadable response (HTTP %s)", response.status_code)
        raise BadGateway(UNCONFIRMED) from exc
    return body if isinstance(body, dict) else {}


def charge(store: StoreSettings, payload: dict, *, idempotency_key: str) -> ChargeResult:
    """Asks the client's API to charge ``payload["token"]``. Raises ``BadRequest`` for a decline, ``BadGateway`` otherwise.

    ``idempotency_key`` (the checkout session id) lets the client return the *same* charge if we have to retry, so a
    timeout can never lead to a double charge.
    """
    body = _exchange(store, payload, idempotency_key)
    status = body.get("status")
    if status == "succeeded" and body.get("id"):
        return ChargeResult(reference=str(body["id"])[:200])
    if status == "declined":
        raise BadRequest(str(body.get("message") or DECLINED)[:200])
    log.warning("Client payment API returned an unsupported result: %r", status)  # e.g. 3-D Secure "requires_action"
    raise BadGateway(UNAVAILABLE)


@dataclass(frozen=True)
class HostedPayment:
    redirect_url: str  # the client's payment page the customer is sent to
    reference: str = ""  # the client's id for this payment attempt, if they gave one


def create_payment(store: StoreSettings, payload: dict, *, idempotency_key: str) -> HostedPayment:
    """Redirect flow: asks the client's API for a payment page. Raises ``BadGateway`` unless it answers with a safe URL.

    The same ``idempotency_key`` must give back the same (or an equivalent) payment page, so retries are safe.
    """
    body = _exchange(store, payload, idempotency_key)
    status, url = body.get("status"), str(body.get("redirect_url") or "").strip()
    if status == "redirect" and _is_safe_redirect(url):
        return HostedPayment(redirect_url=url, reference=str(body.get("id") or "")[:200])
    log.warning("Client payment API returned an unusable payment page: status=%r url=%r", status, url[:80])
    raise BadGateway(UNAVAILABLE)


def _is_safe_redirect(url: str) -> bool:
    parts = urlparse(url)
    if not parts.hostname or len(url) > 2000:
        return False
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1"))


def ping(store: StoreSettings) -> None:
    """Admin "test connection": a signed no-op request. Raises ``BadRequest`` with a human-readable reason."""
    if not store.client_api_url:
        raise BadRequest("Enter and save the client's API URL first")
    try:
        response = _post(store, {"type": "ping"}, idempotency_key="ping")
    except _Unreachable as exc:
        raise BadRequest(f"Couldn't reach the client's API: {exc.detail}") from exc
    if response.status_code in (401, 403):
        raise BadRequest("The client's API rejected our signature. Give them the signing secret shown above.")
    if not response.is_success:
        raise BadRequest(f"The client's API answered HTTP {response.status_code}")
    try:
        ok = response.json().get("ok") is True
    except (ValueError, AttributeError):
        ok = False
    if not ok:
        raise BadRequest('The client\'s API must answer a ping with {"ok": true}')
