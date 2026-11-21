"""Payment attempts: every charge try is recorded, even though a decline rolls back the order itself."""

import pytest

from tests.helpers import ADDRESS

CARD_METHOD = {"id": "card", "label": "Credit card", "type": "card", "instructions": "", "enabled": True}
BANK_METHOD = {"id": "bank", "label": "Bank transfer", "type": "offline", "instructions": "", "enabled": True}


@pytest.fixture
def card(h, client_api):
    h.configure(
        cardProvider="mock",
        cardPublicKey="pk_test_123",
        clientApiUrl=client_api.url,
        paymentMethods=[CARD_METHOD, BANK_METHOD],
    )
    client_api.secret = h.client.get("/api/admin/settings", headers=h.admin).json()["clientApiSecret"]
    return client_api


def pay(h, session_id, token="tok_mock_4242", **overrides):
    body = {
        "customer": {"name": "Ada Lovelace", "email": "ada@example.com"},
        "shipping_address": ADDRESS,
        "payment_method": "card",
        "card_token": token,
        **overrides,
    }
    return h.client.post(f"/api/public/sessions/{session_id}/complete", json=body)


class TestDeclines:
    def test_a_decline_is_recorded_with_its_reason_and_the_session_stays_open(self, h, card):
        session_id = h.create_session()["id"]
        response = pay(h, session_id, token="tok_mock_0002")
        assert response.status_code == 400
        assert response.json()["error"] == "Your card has insufficient funds."

        rows = h.sql("SELECT outcome, reason, attempt_no FROM payment_attempts WHERE session_id = :s", s=session_id)
        assert rows == [("declined", "Your card has insufficient funds.", 1)]
        assert h.client.get(f"/api/public/sessions/{session_id}").json()["status"] == "open"

    def test_a_retry_after_a_decline_succeeds_and_is_recorded_as_recovered(self, h, card):
        session_id = h.create_session()["id"]
        assert pay(h, session_id, token="tok_mock_0002").status_code == 400
        assert pay(h, session_id).status_code == 200

        rows = h.sql(
            "SELECT outcome, attempt_no FROM payment_attempts WHERE session_id = :s ORDER BY attempt_no", s=session_id
        )
        assert rows == [("declined", 1), ("succeeded", 2)]

        out = h.client.get("/api/admin/attempts", headers=h.admin, params={"days": 7}).json()
        assert out["total"] == 2 and out["declined"] == 1 and out["recovered"] == 1
        assert out["by_reason"] == [{"reason": "Your card has insufficient funds.", "count": 1}]

    def test_a_gateway_error_is_recorded_too(self, h, card):
        session_id = h.create_session()["id"]
        assert pay(h, session_id, token="tok_mock_500").status_code == 502
        rows = h.sql("SELECT outcome FROM payment_attempts WHERE session_id = :s", s=session_id)
        assert rows == [("error",)]

    def test_validation_errors_are_not_recorded_as_attempts(self, h, card):
        session_id = h.create_session()["id"]
        response = h.client.post(
            f"/api/public/sessions/{session_id}/complete",
            json={"customer": {"name": "", "email": "a@b.co"}, "shipping_address": ADDRESS, "payment_method": "card"},
        )
        assert response.status_code == 400
        assert h.sql("SELECT COUNT(*) FROM payment_attempts WHERE session_id = :s", s=session_id)[0][0] == 0


class TestRedirectAndManualFailures:
    def test_marking_a_payment_failed_records_an_attempt_and_an_order_event(self, h):
        order = h.place_order("bank")
        h.update_order(order["number"], payment_status="failed")

        rows = h.sql("SELECT outcome FROM payment_attempts WHERE session_id = :s", s=order["session_id"])
        assert rows == [("declined",)]
        order = h.order(order["number"])
        assert any("failed" in e["text"].lower() for e in order["history"])
