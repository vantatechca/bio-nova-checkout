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
    """The shared API key, naming the store the call is about."""
    return {"Authorization": f"Bearer {settings_of(h, store_id)['apiKey']}", "X-Checkout-Store": str(store_id)}


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

    def test_all_stores_share_one_api_key(self, h, two):
        first, second = two
        assert settings_of(h, first["id"])["apiKey"] == settings_of(h, second["id"])["apiKey"]

    def test_the_store_header_accepts_an_id_or_a_slug_and_rejects_unknowns(self, h, two):
        _first, second = two
        key = {"Authorization": f"Bearer {settings_of(h, second['id'])['apiKey']}"}
        body = {"items": [{"name": "X", "unit_amount": 100, "quantity": 1}], "success_url": "https://x.test/ok"}
        by_slug = h.client.post(
            "/api/v1/checkout/sessions", headers={**key, "X-Checkout-Store": second["slug"]}, json=body
        )
        assert by_slug.status_code == 201
        assert (
            h.client.get(
                f"/api/v1/checkout/sessions/{by_slug.json()['id']}", headers=key_of(h, second["id"])
            ).status_code
            == 200
        )
        assert (
            h.client.post(
                "/api/v1/checkout/sessions", headers={**key, "X-Checkout-Store": "nope"}, json=body
            ).status_code
            == 400
        )

    def test_without_the_header_sessions_go_to_the_default_store_and_lookups_cover_all(self, h, two):
        first, second = two
        key = {"Authorization": f"Bearer {settings_of(h, first['id'])['apiKey']}"}
        body = {"items": [{"name": "X", "unit_amount": 100, "quantity": 1}], "success_url": "https://x.test/ok"}
        made = h.client.post("/api/v1/checkout/sessions", headers=key, json=body).json()
        assert h.client.get(f"/api/v1/checkout/sessions/{made['id']}", headers=key).status_code == 200
        b = order_for(h, second["id"])
        assert h.client.get(f"/api/v1/orders/{b['number']}", headers=key).status_code == 200

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


class TestSharedSettings:
    """Card/payment, shipping/tax and webhook settings are shared by every store; branding and Shopify are per store."""

    def test_a_shared_setting_edited_on_one_store_applies_to_all(self, h, two):
        first, second = two
        h.client.put(
            f"/api/admin/settings?store={first['id']}",
            headers=h.admin,
            json={
                "shippingFlat": 700,
                "clientApiUrl": "https://pay.example.com/charge",
                "cardProvider": "embed",
                "cardFormUrl": "https://pay.example.com/form",
            },
        )
        a, b = settings_of(h, first["id"]), settings_of(h, second["id"])
        for field in (
            "shippingFlat",
            "clientApiUrl",
            "cardProvider",
            "cardFormUrl",
            "clientApiSecret",
            "webhookSecret",
            "paymentMethods",
        ):
            assert a[field] == b[field], field
        assert b["shippingFlat"] == 700

    def test_branding_and_shopify_stay_per_store(self, h, two):
        first, second = two
        h.client.put(
            f"/api/admin/settings?store={first['id']}",
            headers=h.admin,
            json={
                "storeName": "Alpha",
                "notice": "A notice",
                "logoUrl": "https://a.example/l.png",
                "storeUrl": A_URL,
                "shopifyDomain": "alpha.myshopify.com",
                "shopifyStorefrontToken": "tok_a",
            },
        )
        b = settings_of(h, second["id"])
        assert b["storeName"] == "Beta Shop" and b["notice"] == "" and b["logoUrl"] == ""
        assert b["storeUrl"] == "" and b["shopifyDomain"] == "" and b["shopifyStorefrontToken"] == ""

    def test_rotating_the_signing_secret_changes_it_for_every_store(self, h, two):
        first, second = two
        new = h.client.post(f"/api/admin/card/rotate-secret?store={first['id']}", headers=h.admin).json()[
            "clientApiSecret"
        ]
        assert settings_of(h, second["id"])["clientApiSecret"] == new

    def test_a_new_store_uses_the_shared_settings_straight_away(self, h):
        h.configure(
            shippingFlat=900,
            cardProvider="embed",
            cardFormUrl="https://pay.example.com/form",
            clientApiUrl="https://pay.example.com/charge",
        )
        new = add_store(h, "Fresh")
        s = settings_of(h, new["id"])
        assert s["shippingFlat"] == 900 and s["clientApiUrl"] == "https://pay.example.com/charge"

    def test_copying_a_store_brings_over_its_branding_only(self, h):
        source = h.client.get("/api/admin/stores", headers=h.admin).json()[0]
        h.configure(
            storeName="Source",
            notice="Shared notice",
            logoUrl="https://s.example/l.png",
            storeUrl=A_URL,
            shopifyDomain="source.myshopify.com",
            shopifyStorefrontToken="tok_source",
        )
        r = h.client.post("/api/admin/stores", headers=h.admin, json={"name": "Copy", "copy_from": source["id"]})
        assert r.status_code == 201, r.text
        new = settings_of(h, r.json()["id"])
        assert new["notice"] == "Shared notice" and new["logoUrl"] == "https://s.example/l.png"
        assert new["storeName"] == "Copy"
        assert new["storeUrl"] == "" and new["shopifyDomain"] == "" and new["shopifyStorefrontToken"] == ""

    def test_copying_from_an_unknown_store_is_a_404(self, h):
        r = h.client.post("/api/admin/stores", headers=h.admin, json={"name": "X", "copy_from": 999})
        assert r.status_code == 404

    def test_an_install_that_predates_sharing_keeps_its_settings(self, h):
        """The shared row is seeded from the first store, so upgrading keeps the card setup and webhook it had."""
        from app.database import session_scope
        from app.repositories import SettingsRepository, StoreRepository
        from app.services.config import config_service, ensure_defaults

        with session_scope() as db:
            row = StoreRepository(db).list()[0]
            row.settings = {**row.settings, "shippingFlat": 1234, "clientApiUrl": "https://old.example.com/charge"}
            db.execute(__import__("sqlalchemy").text("DELETE FROM settings WHERE k = 'shared'"))
        config_service.invalidate()
        with session_scope() as db:
            ensure_defaults(db)
            assert SettingsRepository(db).all()["shared"]["shippingFlat"] == 1234
        config_service.invalidate()
        assert settings_of(h, 1)["clientApiUrl"] == "https://old.example.com/charge"


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

    def test_all_stores_share_the_webhook_and_each_payload_names_its_store(self, h, two, webhook_receiver):
        first, second = two
        h.configure(webhookUrl=webhook_receiver.url)
        order_for(h, first["id"])
        order_for(h, second["id"])
        h.run_worker()
        payloads = [json.loads(w.body) for w in webhook_receiver.received]
        assert {p["data"]["store_id"] for p in payloads} == {first["id"], second["id"]}

    def test_the_settings_log_only_lists_that_stores_webhooks(self, h, two, webhook_receiver):
        first, second = two
        h.configure(webhookUrl=webhook_receiver.url)  # default store
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

    def test_rotating_the_api_key_changes_it_for_every_store(self, h, two):
        first, second = two
        old = settings_of(h, first["id"])["apiKey"]
        r = h.client.post(f"/api/admin/settings/rotate-key?store={second['id']}", headers=h.admin)
        assert r.status_code == 200 and r.json()["apiKey"] != old
        assert settings_of(h, first["id"])["apiKey"] == r.json()["apiKey"]

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
                    text("DELETE FROM settings WHERE k IN ('store', 'shared')"),
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
                store = conn.execute(text("SELECT id, name, shopify_domain FROM stores")).one()
                visit_store = conn.execute(text("SELECT store_id FROM visits")).scalar_one()
                legacy_rows = conn.execute(text("SELECT COUNT(*) FROM settings WHERE k = 'store'")).scalar_one()
            assert tuple(store) == (1, "Legacy Shop", "legacy.myshopify.com")
            config_service.invalidate()
            with engine.begin() as conn:
                from sqlalchemy.orm import Session

                from app.services.config import ensure_defaults

                with Session(conn) as session:
                    ensure_defaults(session)
                    session.flush()
            with engine.connect() as conn:
                shared = json.loads(conn.execute(text("SELECT v FROM settings WHERE k = 'shared'")).scalar_one())
            assert shared["apiKey"] == "sk_legacy_key"
            assert visit_store == 1 and legacy_rows == 0
        finally:
            command.upgrade(cfg, "head")
            config_service.invalidate()
