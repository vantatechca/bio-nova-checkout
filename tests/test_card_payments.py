"""Card payments: the card is tokenized in the processor's fields and charged through the client's own API."""

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.client_payment_api import sign
from tests.helpers import ADDRESS

CARD_METHOD = {"id": "card", "label": "Credit card", "type": "card", "instructions": "", "enabled": True}
BANK_METHOD = {"id": "bank", "label": "Bank transfer", "type": "offline", "instructions": "", "enabled": True}


@pytest.fixture
def card(h, client_api):
    """Card payments configured against the fake client API (signing secret shared the way the client would get it)."""
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
        "customer": {"name": "Ada Lovelace", "email": "ada@example.com", "phone": "555"},
        "shipping_address": ADDRESS,
        "payment_method": "card",
        "card_token": token,
        **overrides,
    }
    return h.client.post(f"/api/public/sessions/{session_id}/complete", json=body)


class TestOfferingCards:
    def test_card_is_hidden_until_the_processor_is_configured(self, h):
        h.configure(paymentMethods=[CARD_METHOD, BANK_METHOD])
        view = h.client.get(f"/api/public/sessions/{h.create_session()['id']}").json()
        assert [m["id"] for m in view["paymentMethods"]] == ["bank"] and view["card"] is None

    def test_card_appears_with_the_publishable_key_only(self, h, card):
        view = h.client.get(f"/api/public/sessions/{h.create_session()['id']}").json()
        assert [(m["id"], m["type"]) for m in view["paymentMethods"]] == [("card", "card"), ("bank", "offline")]
        assert view["card"] == {"provider": "mock", "public_key": "pk_test_123", "form_url": ""}
        assert card.secret not in json.dumps(view)

    def test_embedded_provider_needs_the_clients_card_form_url(self, h, card):
        h.configure(cardProvider="embed", cardFormUrl="")
        view = h.client.get(f"/api/public/sessions/{h.create_session()['id']}").json()
        assert view["card"] is None and [m["id"] for m in view["paymentMethods"]] == ["bank"]
        h.configure(cardProvider="embed", cardFormUrl="https://client.example.com/card-form")
        view = h.client.get(f"/api/public/sessions/{h.create_session()['id']}").json()
        assert view["card"] == {
            "provider": "embed",
            "public_key": "pk_test_123",
            "form_url": "https://client.example.com/card-form",
        }
        assert [m["id"] for m in view["paymentMethods"]] == ["card", "bank"]

    def test_embedded_card_payment_is_charged_through_the_clients_api(self, h, card):
        h.configure(cardProvider="embed", cardFormUrl="https://client.example.com/card-form")
        response = pay(h, h.create_session()["id"])
        assert response.status_code == 200 and response.json()["payment_status"] == "paid"
        assert len(card.charge_requests) == 1

    def test_card_form_url_must_be_https_except_for_local_development(self, h):
        put = lambda url: h.client.put("/api/admin/settings", headers=h.admin, json={"cardFormUrl": url})  # noqa: E731
        assert put("http://client.example.com/form").status_code == 400
        assert put("javascript:alert(1)").status_code == 400
        assert put("client.example.com/form").status_code == 400
        assert put("https://client.example.com/form").status_code == 200
        assert put("http://localhost:9001/embedded_card_form.html").status_code == 200

    def test_a_signing_secret_is_generated_and_stable(self, h):
        first = h.client.get("/api/admin/settings", headers=h.admin).json()["clientApiSecret"]
        h.client.get("/api/admin/settings", headers=h.admin)
        assert (
            first.startswith("capi_")
            and h.client.get("/api/admin/settings", headers=h.admin).json()["clientApiSecret"] == first
        )

    def test_client_api_url_must_be_https_except_for_local_development(self, h):
        put = lambda url: h.client.put("/api/admin/settings", headers=h.admin, json={"clientApiUrl": url})  # noqa: E731
        assert put("http://client.example.com/charge").status_code == 400
        assert put("ftp://client.example.com/charge").status_code == 400
        assert put("client.example.com/charge").status_code == 400
        assert put("https://client.example.com/charge").status_code == 200
        assert put("http://localhost:8000/charge").status_code == 200


class TestChargingACard:
    def test_a_successful_charge_creates_a_paid_order_with_the_charge_reference(self, h, card):
        session = h.create_session(external_ref="cart_1", shipping_amount=500)
        response = pay(h, session["id"])
        assert response.status_code == 200 and response.json()["payment_status"] == "paid"
        assert response.json()["payment_instructions"] == ""
        order = h.order(response.json()["order_number"])
        assert (order["status"], order["payment_status"], order["payment_reference"]) == (
            "processing",
            "paid",
            "ch_test_1",
        )
        assert order["paid_at"] and order["payment_method"] == {"id": "card", "label": "Credit card"}
        assert any("Payment received (ref ch_test_1)" in e["text"] for e in order["history"])

    def test_the_client_api_receives_a_complete_signed_charge_request(self, h, card):
        session = h.create_session(external_ref="cart_1", shipping_amount=500)
        pay(h, session["id"], token="tok_mock_4242")
        request = card.charge_requests[0]
        body = request["body"]
        assert body["type"] == "charge" and body["reference"] == session["id"] and body["order_ref"] == "cart_1"
        assert (body["amount"], body["currency"], body["token"]) == (5500, "USD", "tok_mock_4242")
        assert body["customer"]["email"] == "ada@example.com" and body["shipping_address"]["city"] == "Toronto"
        assert body["items"] == [{"name": "Shirt", "sku": "", "quantity": 2, "unit_amount": 2500}]
        headers = request["headers"]
        assert headers["idempotency-key"] == session["id"]
        expected = (
            "sha256="
            + hmac.new(
                card.secret.encode(), f"{headers['x-checkout-timestamp']}.{request['raw']}".encode(), hashlib.sha256
            ).hexdigest()
        )
        assert headers["x-checkout-signature"] == expected

    def test_the_card_token_is_not_stored_anywhere(self, h, card):
        pay(h, h.create_session()["id"], token="tok_secret_marker_987")
        for table in ("orders", "checkout_sessions", "order_events", "email_log", "webhook_deliveries", "settings"):
            dump = json.dumps([list(map(str, row)) for row in h.sql(f"SELECT * FROM {table}")])
            assert "tok_secret_marker_987" not in dump, table

    def test_paid_by_card_triggers_the_paid_webhook_and_emails_like_other_paid_orders(self, h, card):
        pay(h, h.create_session()["id"])
        assert h.sql("SELECT COUNT(*) FROM webhook_deliveries")[0][0] == 0  # no webhook URL configured
        h.configure(webhookUrl="https://hooks.example.com/x")
        pay(h, h.create_session()["id"])
        events = sorted(r[0] for r in h.sql("SELECT event FROM webhook_deliveries"))
        assert events == ["order.created", "order.paid"]

    def test_the_card_gets_a_decline_message_and_no_order_is_created(self, h, card):
        session = h.create_session()
        response = pay(h, session["id"], token="tok_mock_0002")
        assert response.status_code == 400 and response.json()["error"] == "Your card has insufficient funds."
        assert h.sql("SELECT COUNT(*) FROM orders")[0][0] == 0
        assert h.client.get(f"/api/public/sessions/{session['id']}").json()["status"] == "open"

    def test_after_a_decline_another_card_works_on_the_same_checkout(self, h, card):
        session = h.create_session()
        assert pay(h, session["id"], token="tok_mock_0002").status_code == 400
        assert pay(h, session["id"], token="tok_mock_4242").status_code == 200
        assert h.sql("SELECT COUNT(*) FROM orders")[0][0] == 1

    def test_a_missing_token_is_rejected_before_calling_the_client(self, h, card):
        response = pay(h, h.create_session()["id"], token="")
        assert response.status_code == 400 and response.json()["error"] == "Please enter your card details"
        assert card.charge_requests == []

    def test_other_validation_runs_before_any_charge(self, h, card):
        response = pay(h, h.create_session()["id"], customer={"name": "", "email": "a@b.co"})
        assert response.status_code == 400 and card.charge_requests == []

    def test_double_submission_charges_once(self, h, card):
        session_id = h.create_session()["id"]
        with ThreadPoolExecutor(8) as pool:
            responses = list(pool.map(lambda _: pay(h, session_id), range(8)))
        assert {r.status_code for r in responses} == {200}
        assert len({r.json()["order_number"] for r in responses}) == 1
        assert len(card.charge_requests) == 1  # later submissions get the existing order without charging again

    def test_a_retry_after_a_lost_response_gets_the_same_charge_not_a_second_one(self, h, card):
        session_id = h.create_session()["id"]
        assert pay(h, session_id, token="tok_mock_500").status_code == 502  # the client's API failed mid-way
        assert pay(h, session_id).status_code == 200
        assert pay(h, session_id).status_code == 200
        assert set(card.charges.values()) == {"ch_test_1"} and len(card.charges) == 1


class TestWhenTheClientApiMisbehaves:
    @pytest.mark.parametrize("token", ["tok_mock_500", "tok_mock_garbage", "tok_mock_3ds"])
    def test_failures_become_a_safe_error_and_no_order(self, h, card, token):
        response = pay(h, h.create_session()["id"], token=token)
        assert response.status_code == 502 and response.json()["error"]
        assert "tok_" not in response.text and h.sql("SELECT COUNT(*) FROM orders")[0][0] == 0

    def test_an_unreachable_client_says_the_customer_was_not_charged(self, h, card):
        h.configure(clientApiUrl="http://127.0.0.1:9/charge")
        response = pay(h, h.create_session()["id"])
        assert response.status_code == 502 and "have not been charged" in response.json()["error"]

    def test_a_wrong_signing_secret_is_reported_as_unavailable_not_as_a_decline(self, h, card):
        card.secret = "someone-elses-secret"
        response = pay(h, h.create_session()["id"])
        assert response.status_code == 502 and "temporarily unavailable" in response.json()["error"]
        assert "signature" not in response.text.lower()

    def test_card_payments_stop_working_if_the_processor_is_unconfigured_afterwards(self, h, card):
        session_id = h.create_session()["id"]
        h.configure(clientApiUrl="")
        response = pay(h, session_id)
        assert response.status_code == 400 and "aren't available" in response.json()["error"]


class TestAdminTools:
    def test_test_connection_succeeds_with_the_shared_secret(self, h, card):
        assert h.client.post("/api/admin/card/test", headers=h.admin).json() == {"ok": True}
        assert card.requests[-1]["body"] == {"type": "ping"}

    def test_test_connection_explains_a_signature_problem(self, h, card):
        card.secret = "different"
        response = h.client.post("/api/admin/card/test", headers=h.admin)
        assert response.status_code == 400 and "signature" in response.json()["error"]

    def test_test_connection_needs_a_url_and_an_admin(self, h):
        assert h.client.post("/api/admin/card/test", headers=h.admin).status_code == 400
        assert h.client.post("/api/admin/card/test").status_code == 401

    def test_rotating_the_secret_changes_future_signatures(self, h, card):
        new = h.client.post("/api/admin/card/rotate-secret", headers=h.admin).json()["clientApiSecret"]
        assert new != card.secret and new.startswith("capi_")
        assert h.client.post("/api/admin/card/test", headers=h.admin).status_code == 400  # client still has the old one
        card.secret = new
        assert h.client.post("/api/admin/card/test", headers=h.admin).status_code == 200


class TestSigning:
    def test_signature_is_hmac_sha256_over_timestamp_dot_body(self):
        expected = "sha256=" + hmac.new(b"s3cret", b'1700000000.{"a":1}', hashlib.sha256).hexdigest()
        assert sign("s3cret", "1700000000", '{"a":1}') == expected
        assert sign("other", "1700000000", '{"a":1}') != expected
        assert sign("s3cret", "1700000001", '{"a":1}') != expected  # a replayed body with a new timestamp fails

    def test_existing_installs_get_the_new_settings_backfilled_once(self, h):
        """Settings rows saved before card support existed must gain a *persistent* signing secret."""
        from app.database import session_scope
        from app.repositories import SettingsRepository
        from app.services.config import config_service, ensure_defaults

        with session_scope() as db:
            row = SettingsRepository(db).all()["store"]
            for key in ("clientApiSecret", "clientApiUrl", "cardProvider", "cardPublicKey"):
                row.pop(key, None)
            SettingsRepository(db).set("store", row)
        config_service.invalidate()
        with session_scope() as db:
            ensure_defaults(db)
        config_service.invalidate()
        first = h.client.get("/api/admin/settings", headers=h.admin).json()["clientApiSecret"]
        config_service.invalidate()
        assert h.client.get("/api/admin/settings", headers=h.admin).json()["clientApiSecret"] == first
        assert h.sql("SELECT COUNT(*) FROM settings WHERE k = 'store'")[0][0] == 1


def public_view(h, session_id):
    return h.client.get(f"/api/public/sessions/{session_id}").json()


class TestRedirectPaymentPage:
    """Redirect flow: we ask the client's API for a payment page, the customer pays there, the client marks the order paid."""

    @pytest.fixture
    def redirect(self, h, card):
        h.configure(cardProvider="redirect")
        return card

    def test_redirect_needs_no_card_form_url(self, h, redirect):
        view = public_view(h, h.create_session()["id"])
        assert view["card"]["provider"] == "redirect" and [m["id"] for m in view["paymentMethods"]] == ["card", "bank"]

    def test_pay_creates_a_pending_order_and_returns_the_payment_page(self, h, redirect):
        session = h.create_session(external_ref="cart_9")
        response = pay(h, session["id"], token="")
        assert response.status_code == 200
        out = response.json()
        assert out["redirect_url"] == f"https://pay.client.example/p/{session['id']}"
        assert out["payment_status"] == "pending" and out["payment_instructions"]
        order = h.order(out["order_number"])
        assert (order["status"], order["payment_status"]) == ("pending", "pending")
        assert order["payment_reference"] == f"pay_{session['id'][-6:]}"

    def test_the_client_receives_a_signed_create_payment_with_return_urls_and_no_token(self, h, redirect):
        session = h.create_session()
        pay(h, session["id"], token="")
        (request,) = [r for r in redirect.requests if r["body"].get("type") == "create_payment"]
        body = request["body"]
        assert body["amount"] > 0 and body["reference"] == session["id"] and "token" not in body
        assert body["return_url"] == body["cancel_url"] == f"http://testserver/checkout?session={session['id']}"
        assert request["headers"]["idempotency-key"] == session["id"]
        assert redirect.charge_requests == []

    def test_the_client_marks_the_order_paid_through_the_store_api(self, h, redirect):
        session = h.create_session()
        number = pay(h, session["id"], token="").json()["order_number"]
        h.update_order(number, payment_status="paid", payment_reference="ch_live_1")
        order = h.order(number)
        assert (order["status"], order["payment_status"], order["payment_reference"]) == (
            "processing",
            "paid",
            "ch_live_1",
        )
        view = public_view(h, session["id"])
        assert view.get("payment_status", view.get("paymentStatus")) == "paid"

    @pytest.mark.parametrize("page", ["javascript:alert(1)", "http://pay.client.example/p/1", "not a url", ""])
    def test_an_unsafe_or_missing_payment_page_is_refused_and_no_order_is_created(self, h, redirect, page):
        redirect.payment_page = page or "   "
        response = pay(h, h.create_session()["id"], token="")
        assert response.status_code == 502 and h.sql("SELECT COUNT(*) FROM orders")[0][0] == 0

    def test_a_second_submit_does_not_ask_for_another_payment_page(self, h, redirect):
        session_id = h.create_session()["id"]
        first, second = pay(h, session_id, token=""), pay(h, session_id, token="")
        assert first.json()["order_number"] == second.json()["order_number"] and second.json()["redirect_url"] == ""
        assert len([r for r in redirect.requests if r["body"].get("type") == "create_payment"]) == 1


class TestCardOnlyCheckout:
    def test_when_the_other_methods_are_disabled_card_is_the_only_option(self, h, card):
        offline = [
            {**BANK_METHOD, "enabled": False},
        ]
        h.configure(paymentMethods=[CARD_METHOD, *offline])
        session_id = h.create_session()["id"]
        assert [m["id"] for m in public_view(h, session_id)["paymentMethods"]] == ["card"]
        assert h.complete(session_id, "bank").status_code == 400  # a disabled method can't be forced through
        assert h.sql("SELECT COUNT(*) FROM orders")[0][0] == 0
        assert pay(h, session_id).status_code == 200

    def test_if_card_is_the_only_method_but_unconfigured_nothing_is_offered_and_nothing_is_accepted(self, h):
        h.configure(paymentMethods=[CARD_METHOD])
        session_id = h.create_session()["id"]
        assert public_view(h, session_id)["paymentMethods"] == []
        assert pay(h, session_id).status_code == 400


class TestTestProviderSafeguard:
    """The fake provider approves any test card, so it must never be live on a public https site."""

    def test_it_is_refused_on_a_public_https_site(self, h, card, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "public_url", "https://checkout.example.com")
        session_id = h.create_session()["id"]
        view = public_view(h, session_id)
        assert view["card"] is None and "card" not in [m["id"] for m in view["paymentMethods"]]
        response = pay(h, session_id)
        assert response.status_code == 400 and "aren't available" in response.json()["error"]
        assert card.charge_requests == [] and h.sql("SELECT COUNT(*) FROM orders")[0][0] == 0

    def test_it_can_be_explicitly_allowed_for_a_staging_site(self, h, card, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "public_url", "https://staging.example.com")
        monkeypatch.setattr(get_settings(), "allow_test_card_provider", True)
        session_id = h.create_session()["id"]
        assert public_view(h, session_id)["card"] == {"provider": "mock", "public_key": "pk_test_123", "form_url": ""}
        assert pay(h, session_id).status_code == 200

    def test_a_real_provider_is_not_affected_by_the_https_rule(self, h, card, monkeypatch):
        from app.config import get_settings

        h.configure(cardProvider="stripe")  # any provider other than the fake one
        monkeypatch.setattr(get_settings(), "public_url", "https://checkout.example.com")
        assert public_view(h, h.create_session()["id"])["card"]["provider"] == "stripe"
