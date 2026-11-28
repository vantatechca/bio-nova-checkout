"""X8: pending_since tracking and the automatic expiry sweep for stale redirect-flow payments.

A signed, idempotent webhook that marks orders paid already existed (docs/redirect-payment.md step 4 -- the
``PATCH /api/v1/orders/{id}`` the payment partner calls, authenticated the same way every store-API call is,
and explicitly documented as safe to call again with the same values). What was missing was handling the case
where that webhook simply never arrives.
"""

import json
from datetime import datetime, timedelta

import pytest

from app.models.types import utcnow
from app.services.orders import expire_stale_pending_payments
from tests.helpers import ADDRESS

CARD_METHOD = {"id": "card", "label": "Credit card", "type": "card", "instructions": "", "enabled": True}
BANK_METHOD = {"id": "bank", "label": "Bank transfer", "type": "offline", "instructions": "", "enabled": True}


@pytest.fixture
def redirect(h, client_api):
    """Redirect-flow card payments against the fake client API (same fixture shape as test_card_payments.py)."""
    h.configure(cardProvider="redirect", clientApiUrl=client_api.url, paymentMethods=[CARD_METHOD, BANK_METHOD])
    client_api.secret = h.client.get("/api/admin/settings", headers=h.admin).json()["clientApiSecret"]
    return client_api


def pay(h, session_id):
    body = {
        "customer": {"name": "Ada Lovelace", "email": "ada@example.com", "phone": "555"},
        "shipping_address": ADDRESS,
        "payment_method": "card",
    }
    return h.client.post(f"/api/public/sessions/{session_id}/complete", json=body)


def _order_number(h) -> int:
    return h.sql("SELECT number FROM orders")[0][0]


def _age(h, number: int, hours: float) -> None:
    old = (utcnow() - timedelta(hours=hours)).replace(tzinfo=None)
    h.sql("UPDATE orders SET pending_since = :t WHERE number = :n", t=old, n=number)


class TestPendingSince:
    def test_a_redirect_payment_order_starts_with_pending_since_set(self, h, redirect):
        pay(h, h.create_session()["id"])
        order = h.order(_order_number(h))
        assert order["payment_status"] == "pending" and order["pending_since"] is not None

    def test_an_offline_order_also_gets_pending_since(self, h):
        order = h.place_order("bank")
        assert order["payment_status"] == "pending" and order["pending_since"] is not None

    def test_marking_paid_clears_pending_since(self, h, redirect):
        pay(h, h.create_session()["id"])
        number = _order_number(h)
        h.update_order(number, paymentStatus="paid")
        order = h.order(number)
        assert order["payment_status"] == "paid" and order["pending_since"] is None

    def test_marking_failed_then_pending_again_resets_the_clock(self, h, redirect):
        pay(h, h.create_session()["id"])
        number = _order_number(h)
        _age(h, number, hours=48)
        h.update_order(number, paymentStatus="failed")
        assert h.order(number)["pending_since"] is None
        h.update_order(number, paymentStatus="pending")
        pending_since = h.order(number)["pending_since"]
        assert pending_since is not None
        parsed = datetime.fromisoformat(pending_since.replace("Z", "+00:00"))
        assert (utcnow() - parsed) < timedelta(seconds=30)  # reset to "now", not the 48h-old value


class TestExpiry:
    def test_a_stale_redirect_payment_is_marked_failed(self, h, redirect):
        pay(h, h.create_session()["id"])
        number = _order_number(h)
        _age(h, number, hours=25)
        assert expire_stale_pending_payments() == 1
        order = h.order(number)
        assert order["payment_status"] == "failed" and order["pending_since"] is None
        assert "Automatically marked failed" in order["history"][-1]["text"]

    def test_a_fresh_redirect_payment_is_left_alone(self, h, redirect):
        pay(h, h.create_session()["id"])
        number = _order_number(h)
        assert expire_stale_pending_payments() == 0
        assert h.order(number)["payment_status"] == "pending"

    def test_offline_orders_are_never_auto_expired_no_matter_how_old(self, h):
        order = h.place_order("bank")
        _age(h, order["number"], hours=24 * 30)
        assert expire_stale_pending_payments() == 0
        assert h.order(order["number"])["payment_status"] == "pending"

    def test_an_already_paid_order_is_never_touched_even_if_it_looks_old(self, h, redirect):
        pay(h, h.create_session()["id"])
        number = _order_number(h)
        h.update_order(number, paymentStatus="paid")
        # pending_since is already None (cleared on payment), so this order was never a candidate in the first
        # place -- the real race-safety guarantee (re-check under lock) is in the code, not reproducible here
        # without true concurrency, but this confirms a paid order can't be reached by the sweep at all.
        assert expire_stale_pending_payments() == 0
        assert h.order(number)["payment_status"] == "paid"

    def test_queues_the_order_updated_webhook(self, h, redirect, webhook_receiver):
        h.configure(webhookUrl=webhook_receiver.url)
        pay(h, h.create_session()["id"])
        number = _order_number(h)
        _age(h, number, hours=25)
        expire_stale_pending_payments()

        from app.workers.outbox import OutboxProcessor

        OutboxProcessor().run_once()
        events = [json.loads(r.body)["event"] for r in webhook_receiver.received]
        assert "order.updated" in events


class TestNoOrderDiagnostics:
    """X8: "a look at why 2 pay clicks produced no order." An actual decline or an unreachable payment partner
    already left a trace in payment_attempts (app/api/public.py's existing BadRequest/BadGateway handling) --
    the gap was a genuinely unexpected failure (a bug, a timeout nothing already wraps), which left nothing but
    a traceback in the server's own logs. This confirms that gap is closed, and that it's closed precisely:
    not logged for routing-level cases (a missing or expired session) that were never a payment attempt at all.
    """

    def test_an_unexpected_error_during_complete_session_is_recorded(self, h, monkeypatch):
        from app.services import checkout

        def boom(*args, **kwargs):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(checkout, "complete_session", boom)
        session = h.create_session()
        response = h.complete(session["id"], "bank")
        assert response.status_code == 500
        rows = h.sql("SELECT outcome, reason FROM payment_attempts WHERE session_id = :s", s=session["id"])
        assert len(rows) == 1 and rows[0][0] == "error" and "simulated crash" in rows[0][1]

    def test_a_missing_session_is_not_logged_as_a_payment_attempt(self, h):
        response = h.complete("cs_missing", "bank")
        assert response.status_code == 404
        assert h.sql("SELECT COUNT(*) FROM payment_attempts")[0][0] == 0

    def test_an_expired_session_is_not_logged_as_a_payment_attempt(self, h):
        session = h.create_session()
        h.sql("UPDATE checkout_sessions SET expires_at = :t WHERE id = :s", t=utcnow() - timedelta(days=1), s=session["id"])
        response = h.complete(session["id"], "bank")
        assert response.status_code == 410
        assert h.sql("SELECT COUNT(*) FROM payment_attempts")[0][0] == 0
