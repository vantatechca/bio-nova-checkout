"""One checkout serving several stores: data, credentials and configuration stay separate per store."""

import json

import pytest

from tests.helpers import ADDRESS
from tests.support import FakeShopify

A_URL, B_URL = "https://alpha.example", "https://beta.example"


def add_store(h, name: str, **settings) -> dict:
    r = h.client.post("/api/admin/stores", headers=h.admin, json={"name": name})
    assert r.status_code == 201, r.text
    store = r.json()
    if settings:
        r = h.client.put(f"/api/admin/settings?store={store['id']}", headers=h.admin, json=settings)
        assert r.status_code == 200, r.text
    return store


def settings_of(h, store_id: int) -> dict:
    return h.client.get(f"/api/admin/settings?store={store_id}", headers=h.admin).json()


def key_of(h, store_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings_of(h, store_id)['apiKey']}"}


def order_for(h, store_id: int, method="bank") -> dict:
    """A placed order for the given store, made through that store's own API key."""
    r = h.client.post(
        "/api/v1/checkout/sessions",
        headers=key_of(h, store_id),
        json={"items": [{"name": "Shirt", "unit_amount": 2500, "quantity": 2}], "success_url": "https://x.test/ok"},
    )
    assert r.status_code == 201, r.text
    session = r.json()
    body = {
        "customer": {"name": "Ada", "email": "ada@example.com"},
        "shipping_address": ADDRESS,
        "payment_method": method,
    }
    done = h.client.post(f"/api/public/sessions/{session['id']}/complete", json=body)
    assert done.status_code == 200, done.text
    return h.order(done.json()["order_number"])


@pytest.fixture
def two(h):
    first = h.client.get("/api/admin/stores", headers=h.admin).json()[0]
    second = add_store(h, "Beta Shop")
    return first, second


class TestStoresAreSeparate:
    def test_a_fresh_install_has_one_default_store(self, h):
        stores = h.client.get("/api/admin/stores", headers=h.admin).json()
        assert len(stores) == 1 and stores[0]["active"]

    def test_each_store_has_its_own_api_key(self, h, two):
        first, second = two
        assert settings_of(h, first["id"])["apiKey"] != settings_of(h, second["id"])["apiKey"]

    def test_orders_belong_to_the_store_whose_key_created_them(self, h, two):
        first, second = two
        a, b = order_for(h, first["id"]), order_for(h, second["id"])
        assert a["store_id"] == first["id"] and b["store_id"] == second["id"]

    def test_a_store_cannot_see_or_change_another_stores_data(self, h, two):
        first, second = two
        a, b = order_for(h, first["id"]), order_for(h, second["id"])
        mine = key_of(h, first["id"])
        listed = h.client.get("/api/v1/orders", headers=mine).json()["data"]
        assert [o["number"] for o in listed] == [a["number"]]
        assert h.client.get(f"/api/v1/orders/{b['number']}", headers=mine).status_code == 404
        r = h.client.patch(f"/api/v1/orders/{b['number']}", headers=mine, json={"payment_status": "paid"})
        assert r.status_code == 404
        assert h.order(b["number"])["payment_status"] == "pending"

    def test_a_store_cannot_read_another_stores_session(self, h, two):
        first, second = two
        r = h.client.post(
            "/api/v1/checkout/sessions",
            headers=key_of(h, second["id"]),
            json={"items": [{"name": "X", "unit_amount": 100, "quantity": 1}], "success_url": "https://x.test/ok"},
        )
        sid = r.json()["id"]
        assert h.client.get(f"/api/v1/checkout/sessions/{sid}", headers=key_of(h, second["id"])).status_code == 200
        assert h.client.get(f"/api/v1/checkout/sessions/{sid}", headers=key_of(h, first["id"])).status_code == 404

    def test_a_disabled_store_cannot_use_the_api(self, h, two):
        _first, second = two
        headers = key_of(h, second["id"])
        assert (
            h.client.patch(f"/api/admin/stores/{second['id']}", headers=h.admin, json={"active": False}).status_code
            == 200
        )
        r = h.client.post(
            "/api/v1/checkout/sessions",
            headers=headers,
            json={"items": [{"name": "X", "unit_amount": 100, "quantity": 1}], "success_url": "https://x.test/ok"},
        )
        assert r.status_code == 401

    def test_the_last_active_store_cannot_be_disabled(self, h):
        only = h.client.get("/api/admin/stores", headers=h.admin).json()[0]
        r = h.client.patch(f"/api/admin/stores/{only['id']}", headers=h.admin, json={"active": False})
        assert r.status_code == 400


class TestCopyingSettings:
    def test_a_copied_store_inherits_card_and_branding_but_not_identity(self, h):
        source = h.client.get("/api/admin/stores", headers=h.admin).json()[0]
        h.configure(
            storeName="Source",
            notice="Shared notice",
            shippingFlat=700,
            clientApiUrl="https://pay.example.com/charge",
            cardProvider="embed",
            cardFormUrl="https://pay.example.com/form",
            storeUrl=A_URL,
            shopifyDomain="source.myshopify.com",
            shopifyStorefrontToken="tok_source",
            webhookUrl="https://hooks.example.com/source",
        )
        r = h.client.post("/api/admin/stores", headers=h.admin, json={"name": "Copy", "copy_from": source["id"]})
        assert r.status_code == 201, r.text
        new, old = settings_of(h, r.json()["id"]), settings_of(h, source["id"])

        for shared in ("notice", "shippingFlat", "clientApiUrl", "cardProvider", "cardFormUrl", "clientApiSecret"):
            assert new[shared] == old[shared], shared
        assert new["storeName"] == "Copy"
        for own in ("apiKey", "webhookSecret"):
            assert new[own] != old[own], own
        assert new["shopifyDomain"] == "" and new["shopifyStorefrontToken"] == ""
        assert new["storeUrl"] == "" and new["webhookUrl"] == ""

    def test_the_source_store_is_left_untouched(self, h):
        source = h.client.get("/api/admin/stores", headers=h.admin).json()[0]
        before = settings_of(h, source["id"])
        h.client.post("/api/admin/stores", headers=h.admin, json={"name": "Copy", "copy_from": source["id"]})
        assert settings_of(h, source["id"]) == before

    def test_copying_from_an_unknown_store_is_a_404(self, h):
        r = h.client.post("/api/admin/stores", headers=h.admin, json={"name": "X", "copy_from": 999})
        assert r.status_code == 404


class TestPerStoreConfiguration:
    def test_branding_and_payment_methods_follow_the_stores_settings(self, h, two):
        first, second = two
        h.client.put(
            f"/api/admin/settings?store={second['id']}",
            headers=h.admin,
            json={"storeName": "Beta Shop", "notice": "Beta notice", "logoUrl": "https://beta.example/logo.png"},
        )
        a_session = h.client.post(
            "/api/v1/checkout/sessions",
            headers=key_of(h, first["id"]),
            json={"items": [{"name": "X", "unit_amount": 100, "quantity": 1}], "success_url": "https://x.test/ok"},
        ).json()["id"]
        b_session = h.client.post(
            "/api/v1/checkout/sessions",
            headers=key_of(h, second["id"]),
            json={"items": [{"name": "X", "unit_amount": 100, "quantity": 1}], "success_url": "https://x.test/ok"},
        ).json()["id"]
        a_view = h.client.get(f"/api/public/sessions/{a_session}").json()
        b_view = h.client.get(f"/api/public/sessions/{b_session}").json()
        assert b_view["storeName"] == "Beta Shop" and b_view["branding"]["notice"] == "Beta notice"
        assert a_view["storeName"] != "Beta Shop" and a_view["branding"]["notice"] != "Beta notice"

    def test_webhooks_go_to_each_stores_own_endpoint(self, h, two, webhook_receiver):
        first, second = two
        h.client.put(
            f"/api/admin/settings?store={second['id']}", headers=h.admin, json={"webhookUrl": webhook_receiver.url}
        )
        order_for(h, first["id"])
        assert h.run_worker() == 0  # the first store has no webhook configured
        order_for(h, second["id"])
        h.run_worker()
        payloads = [json.loads(w.body) for w in webhook_receiver.received]
        assert {p["event"] for p in payloads} >= {"order.created"}
        assert all(p["data"]["store_id"] == second["id"] for p in payloads)

    def test_the_settings_log_only_lists_that_stores_webhooks(self, h, two, webhook_receiver):
        first, second = two
        h.configure(webhookUrl=webhook_receiver.url)  # default store
        h.client.put(
            f"/api/admin/settings?store={second['id']}", headers=h.admin, json={"webhookUrl": webhook_receiver.url}
        )
        a, b = order_for(h, first["id"]), order_for(h, second["id"])
        log_a = {e["order"] for e in settings_of(h, first["id"])["webhookLog"]}
        log_b = {e["order"] for e in settings_of(h, second["id"])["webhookLog"]}
        assert log_a == {a["number"]} and log_b == {b["number"]}

    def test_confirmation_emails_use_the_stores_name(self, h, two, smtp_server):
        _first, second = two
        h.configure_smtp(smtp_server)
        h.client.put(f"/api/admin/settings?store={second['id']}", headers=h.admin, json={"storeName": "Beta Shop"})
        order_for(h, second["id"])
        h.run_worker()
        assert any("Beta Shop" in mail.subject for mail in smtp_server.mails)

    def test_two_stores_cannot_share_a_shopify_domain(self, h, two):
        first, second = two
        h.client.put(
            f"/api/admin/settings?store={first['id']}", headers=h.admin, json={"shopifyDomain": "dup.myshopify.com"}
        )
        r = h.client.put(
            f"/api/admin/settings?store={second['id']}", headers=h.admin, json={"shopifyDomain": "dup.myshopify.com"}
        )
        assert r.status_code == 400

    def test_rotating_a_key_only_affects_that_store(self, h, two):
        first, second = two
        old_first = key_of(h, first["id"])
        r = h.client.post(f"/api/admin/settings/rotate-key?store={second['id']}", headers=h.admin)
        assert r.status_code == 200 and r.json()["apiKey"] != settings_of(h, first["id"])["apiKey"]
        assert key_of(h, first["id"]) == old_first

    def test_unknown_store_is_a_404(self, h):
        assert h.client.get("/api/admin/settings?store=9999", headers=h.admin).status_code == 404
        assert h.client.get("/api/admin/orders?store=9999", headers=h.admin).status_code == 404


class TestAdminViews:
    def test_orders_can_be_filtered_by_store(self, h, two):
        first, second = two
        a, b = order_for(h, first["id"]), order_for(h, second["id"])
        everything = h.client.get("/api/admin/orders", headers=h.admin).json()["data"]
        only_b = h.client.get(f"/api/admin/orders?store={second['id']}", headers=h.admin).json()["data"]
        assert {o["number"] for o in everything} == {a["number"], b["number"]}
        assert [o["number"] for o in only_b] == [b["number"]]

    def test_stats_and_revenue_are_per_store(self, h, two):
        first, second = two
        order_for(h, first["id"], method="test")
        order_for(h, second["id"])
        everything = h.client.get("/api/admin/stats", headers=h.admin).json()
        only_a = h.client.get(f"/api/admin/stats?store={first['id']}", headers=h.admin).json()
        only_b = h.client.get(f"/api/admin/stats?store={second['id']}", headers=h.admin).json()
        assert everything["total_orders"] == 2 and only_a["total_orders"] == 1 and only_b["total_orders"] == 1
        assert only_a["paid_revenue"] == 5000 and only_b["paid_revenue"] == 0
        revenue_b = h.client.get(f"/api/admin/revenue?store={second['id']}", headers=h.admin).json()
        assert revenue_b["all_time"] == 0

    def test_visits_are_counted_per_store(self, h, two):
        first, second = two
        for store, ip in ((first, "1.1.1.1"), (second, "2.2.2.2")):
            sid = h.client.post(
                "/api/v1/checkout/sessions",
                headers=key_of(h, store["id"]),
                json={"items": [{"name": "X", "unit_amount": 100, "quantity": 1}], "success_url": "https://x.test/ok"},
            ).json()["id"]
            h.client.get(f"/api/public/sessions/{sid}", headers={"X-Forwarded-For": ip, "User-Agent": f"Mozilla {ip}"})
        total = h.client.get("/api/admin/visits", headers=h.admin).json()["views"]
        only_a = h.client.get(f"/api/admin/visits?store={first['id']}", headers=h.admin).json()["views"]
        assert total == 2 and only_a == 1

    def test_stores_list_shows_order_counts(self, h, two):
        first, second = two
        order_for(h, second["id"])
        counts = {s["id"]: s["orders"] for s in h.client.get("/api/admin/stores", headers=h.admin).json()}
        assert counts == {first["id"]: 0, second["id"]: 1}

    def test_stores_with_orders_cannot_be_deleted_but_empty_ones_can(self, h, two):
        first, second = two
        order_for(h, second["id"])
        assert h.client.delete(f"/api/admin/stores/{second['id']}", headers=h.admin).status_code == 400
        assert h.client.delete(f"/api/admin/stores/{first['id']}", headers=h.admin).status_code == 204
        assert h.client.delete(f"/api/admin/stores/{second['id']}", headers=h.admin).status_code == 400  # the last one


class TestShopifyWithSeveralStores:
    @pytest.fixture
    def shops(self, h, shopify, two):
        first, second = two
        for store, url, domain in ((first, A_URL, "alpha.myshopify.com"), (second, B_URL, "beta.myshopify.com")):
            r = h.client.put(
                f"/api/admin/settings?store={store['id']}",
                headers=h.admin,
                json={"storeUrl": url, "shopifyDomain": domain, "shopifyStorefrontToken": FakeShopify.TOKEN},
            )
            assert r.status_code == 200, r.text
        shopify.variants = {11: FakeShopify.variant("Logo T-shirt", "25.00")}
        return first, second

    def _post(self, h, origin=None, shop=""):
        headers = {"Origin": origin} if origin else {}
        return h.client.post(
            "/api/shopify/checkout", json={"items": [{"variant_id": 11, "quantity": 1}], "shop": shop}, headers=headers
        )

    def _session_store(self, h, response) -> int:
        sid = response.json()["checkout_url"].split("=")[1]
        return h.sql("SELECT store_id FROM checkout_sessions WHERE id = :i", i=sid)[0][0]

    def test_the_origin_decides_which_store_the_cart_belongs_to(self, h, shops):
        first, second = shops
        r = self._post(h, origin=B_URL)
        assert r.status_code == 200 and self._session_store(h, r) == second["id"]
        assert r.headers["access-control-allow-origin"] == B_URL
        r = self._post(h, origin=A_URL)
        assert self._session_store(h, r) == first["id"]

    def test_the_shop_domain_is_used_when_the_origin_does_not_match(self, h, shops):
        _first, second = shops
        r = self._post(h, origin="https://preview.example", shop="beta.myshopify.com")
        assert r.status_code == 200 and self._session_store(h, r) == second["id"]
        assert "access-control-allow-origin" not in r.headers  # an unknown origin never gets to read the answer

    def test_an_unknown_website_is_refused(self, h, shops):
        r = self._post(h, origin="https://stranger.example")
        assert r.status_code == 400

    def test_without_any_identification_several_stores_are_ambiguous(self, h, shops):
        assert self._post(h).status_code == 400

    def test_preflight_allows_any_connected_storefront_only(self, h, shops):
        ok = h.client.options(
            "/api/shopify/checkout", headers={"Origin": B_URL, "Access-Control-Request-Method": "POST"}
        )
        bad = h.client.options(
            "/api/shopify/checkout",
            headers={"Origin": "https://stranger.example", "Access-Control-Request-Method": "POST"},
        )
        assert ok.headers.get("access-control-allow-origin") == B_URL
        assert "access-control-allow-origin" not in bad.headers

    def test_two_stores_cannot_claim_the_same_website(self, h, shops):
        _first, second = shops
        r = h.client.put(f"/api/admin/settings?store={second['id']}", headers=h.admin, json={"storeUrl": A_URL})
        assert r.status_code == 400


class TestMigration:
    def test_an_existing_single_store_install_keeps_its_data_and_api_key(self, client):
        """0001 -> 0002: the legacy settings row becomes store #1 with the same API key; rows are assigned to it."""
        from alembic import command
        from sqlalchemy import text

        from app.database import get_engine
        from app.migrate import alembic_config
        from app.services.config import config_service

        cfg = alembic_config()
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for table in ("order_items", "order_events", "orders", "checkout_sessions", "visits", "stores"):
                conn.execute(text(f"TRUNCATE TABLE `{table}`"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        try:
            command.downgrade(cfg, "0001")
            with engine.begin() as conn:
                legacy = {
                    "storeName": "Legacy Shop",
                    "apiKey": "sk_legacy_key",
                    "shopifyDomain": "legacy.myshopify.com",
                }
                conn.execute(
                    text("DELETE FROM settings WHERE k = 'store'"),
                )
                conn.execute(text("INSERT INTO settings (k, v) VALUES ('store', :v)"), {"v": json.dumps(legacy)})
                conn.execute(
                    text(
                        "INSERT INTO visits (at, session_id, visitor, device, referrer) "
                        "VALUES (NOW(3), 'cs_old', 'abc', 'desktop', '')"
                    )
                )
            command.upgrade(cfg, "head")
            with engine.connect() as conn:
                store = conn.execute(text("SELECT id, name, api_key, shopify_domain FROM stores")).one()
                visit_store = conn.execute(text("SELECT store_id FROM visits")).scalar_one()
                legacy_rows = conn.execute(text("SELECT COUNT(*) FROM settings WHERE k = 'store'")).scalar_one()
            assert tuple(store) == (1, "Legacy Shop", "sk_legacy_key", "legacy.myshopify.com")
            assert visit_store == 1 and legacy_rows == 0
        finally:
            command.upgrade(cfg, "head")
            config_service.invalidate()
