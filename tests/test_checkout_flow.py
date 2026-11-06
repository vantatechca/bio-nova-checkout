from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from app.database import get_engine
from tests.helpers import CART


class TestCreatingSessions:
    def test_returns_checkout_link_and_totals(self, h):
        session = h.create_session(shipping_amount=500, external_ref="cart_1")
        assert session["checkout_url"] == f"http://testserver/checkout?session={session['id']}"
        assert (session["subtotal"], session["shipping"], session["tax"], session["total"]) == (5000, 500, 0, 5500)
        assert session["status"] == "open" and session["external_ref"] == "cart_1"

    def test_uses_store_defaults_for_shipping_and_tax(self, h):
        h.configure(shippingFlat=700, taxRatePercent=13)
        session = h.create_session()
        assert (session["shipping"], session["tax"], session["total"]) == (700, 650, 6350)

    def test_store_supplied_shipping_and_tax_override_defaults(self, h):
        h.configure(shippingFlat=700, taxRatePercent=13)
        session = h.create_session(shipping_amount=0, tax_amount=0)
        assert session["total"] == 5000

    def test_requires_api_key(self, client):
        r = client.post("/api/v1/checkout/sessions", json={"items": CART, "success_url": "https://a.test"})
        assert r.status_code == 401 and r.json() == {"error": "Invalid or missing API key"}

    def test_rejects_fractional_amounts(self, h):
        r = h.client.post(
            "/api/v1/checkout/sessions",
            headers=h.store,
            json={"items": [{"name": "x", "unit_amount": 1.5}], "success_url": "https://a.test"},
        )
        assert r.status_code == 400 and "unit_amount" in r.json()["error"]

    def test_rejects_empty_cart_and_missing_success_url(self, h):
        assert (
            h.client.post(
                "/api/v1/checkout/sessions", headers=h.store, json={"items": [], "success_url": "https://a.test"}
            ).status_code
            == 400
        )
        assert h.client.post("/api/v1/checkout/sessions", headers=h.store, json={"items": CART}).status_code == 400

    def test_rejects_non_http_redirects(self, h):
        r = h.client.post(
            "/api/v1/checkout/sessions", headers=h.store, json={"items": CART, "success_url": "javascript:alert(1)"}
        )
        assert r.status_code == 400 and "success_url" in r.json()["error"]

    def test_allowed_domains_restrict_redirects(self, h):
        h.configure(allowedDomains="shop.test")
        ok = h.client.post(
            "/api/v1/checkout/sessions",
            headers=h.store,
            json={"items": CART, "success_url": "https://www.shop.test/thanks"},
        )
        evil = h.client.post(
            "/api/v1/checkout/sessions",
            headers=h.store,
            json={"items": CART, "success_url": "https://evil.test/thanks"},
        )
        lookalike = h.client.post(
            "/api/v1/checkout/sessions", headers=h.store, json={"items": CART, "success_url": "https://notshop.test/x"}
        )
        assert ok.status_code == 201
        assert evil.status_code == 400 and lookalike.status_code == 400

    def test_session_can_be_fetched_by_the_store(self, h):
        session = h.create_session()
        r = h.client.get(f"/api/v1/checkout/sessions/{session['id']}", headers=h.store)
        assert r.status_code == 200 and r.json()["id"] == session["id"]
        assert h.client.get("/api/v1/checkout/sessions/cs_nope", headers=h.store).status_code == 404


class TestCustomerPage:
    def test_public_view_has_no_secrets_and_fills_payment_instructions(self, h):
        session = h.create_session()
        r = h.client.get(f"/api/public/sessions/{session['id']}")
        body = r.json()
        assert r.headers["access-control-allow-origin"] == "*"
        assert body["storeName"] == "My Store" and body["total"] == 5000
        interac = next(m for m in body["paymentMethods"] if m["id"] == "interac")
        assert "$50.00" in interac["instructions"] and "{total}" not in interac["instructions"]
        assert "apiKey" not in r.text and "webhookSecret" not in r.text

    def test_unknown_session_is_404(self, client):
        assert client.get("/api/public/sessions/cs_missing").status_code == 404

    def test_disabled_payment_methods_are_hidden_and_rejected(self, h):
        methods = [
            {"id": "cod", "label": "COD", "type": "offline", "instructions": "", "enabled": False},
            {"id": "zelle", "label": "Zelle", "type": "offline", "instructions": "", "enabled": True},
        ]
        h.configure(paymentMethods=methods)
        session = h.create_session()
        shown = [m["id"] for m in h.client.get(f"/api/public/sessions/{session['id']}").json()["paymentMethods"]]
        assert shown == ["zelle"]
        assert h.complete(session["id"], "cod").status_code == 400


class TestPlacingOrders:
    def test_offline_payment_leaves_order_pending_with_instructions(self, h):
        session = h.create_session(external_ref="cart_9")
        r = h.complete(session["id"], "interac")
        body = r.json()
        assert r.status_code == 200 and body["order_number"] == 1001 and body["payment_status"] == "pending"
        assert "Order #1001" in body["payment_instructions"]
        assert body["success_url"] == f"https://shop.test/thanks?checkout_session={session['id']}&order=1001&ref=cart_9"
        order = h.order(1001)
        assert (order["status"], order["payment_status"], order["paid_at"]) == ("pending", "pending", None)
        assert order["items"][0]["name"] == "Shirt" and order["shipping_address"]["city"] == "Toronto"

    def test_test_gateway_marks_order_paid_immediately(self, h):
        order = h.place_order("test")
        assert (order["status"], order["payment_status"]) == ("processing", "paid") and order["paid_at"]

    def test_success_url_keeps_existing_query_string(self, h):
        session = h.create_session(success_url="https://shop.test/thanks?lang=fr")
        url = h.complete(session["id"], "cod").json()["success_url"]
        assert "lang=fr" in url and "order=1001" in url

    def test_validation_messages_are_friendly(self, h):
        sid = h.create_session()["id"]
        assert h.complete(sid, customer={"name": "", "email": "a@b.co"}).json()["error"] == "Name is required"
        assert h.complete(sid, customer={"name": "A", "email": "nope"}).json()["error"] == "A valid email is required"
        assert (
            h.complete(sid, shipping_address={"line1": "x"}).json()["error"] == "Please complete the shipping address"
        )
        assert h.complete(sid, "bitcoin").json()["error"] == "Please choose a payment method"
        assert h.sql("SELECT COUNT(*) FROM orders")[0][0] == 0

    def test_placing_twice_returns_the_same_order(self, h):
        sid = h.create_session()["id"]
        first, second = h.complete(sid).json(), h.complete(sid).json()
        assert first["order_number"] == second["order_number"]
        assert h.sql("SELECT COUNT(*) FROM orders")[0][0] == 1

    def test_ten_simultaneous_submissions_create_exactly_one_order(self, h):
        sid = h.create_session()["id"]
        with ThreadPoolExecutor(10) as pool:
            responses = list(pool.map(lambda _: h.complete(sid), range(10)))
        assert {r.status_code for r in responses} == {200}
        assert len({r.json()["order_number"] for r in responses}) == 1
        assert h.sql("SELECT COUNT(*) FROM orders")[0][0] == 1

    def test_parallel_orders_get_unique_sequential_numbers(self, h):
        sessions = [h.create_session(external_ref=f"c{i}")["id"] for i in range(30)]
        with ThreadPoolExecutor(10) as pool:
            numbers = [r.json()["order_number"] for r in pool.map(h.complete, sessions)]
        assert sorted(numbers) == list(range(1001, 1031))

    def test_expired_sessions_cannot_be_completed(self, h):
        sid = h.create_session()["id"]
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE checkout_sessions SET expires_at = '2020-01-01' WHERE id = :i"), {"i": sid})
        r = h.complete(sid)
        assert r.status_code == 410
        assert h.client.get(f"/api/public/sessions/{sid}").json()["status"] == "expired"

    def test_page_shows_completed_state_after_ordering(self, h):
        sid = h.create_session()["id"]
        h.complete(sid, "zelle")
        view = h.client.get(f"/api/public/sessions/{sid}").json()
        assert view["status"] == "complete" and view["order_number"] == 1001
        assert view["payment_status"] == "pending" and "Order #1001" in view["payment_instructions"]
