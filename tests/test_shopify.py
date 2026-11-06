"""The Shopify connector: a storefront cart becomes a checkout session priced by Shopify, never by the browser."""

import pytest

from app.security import shopify_limiter
from tests.support import FakeShopify

STORE = "https://shop.example"


@pytest.fixture
def connected(h, shopify):
    """Shopify connected, with a T-shirt (id 11, $25.00, in two sizes) and a mug (id 12, $12.50)."""
    h.configure(
        storeUrl=STORE,
        shopifyDomain="my-shop.myshopify.com",
        shopifyStorefrontToken=FakeShopify.TOKEN,
    )
    shopify.variants = {
        11: FakeShopify.variant("Logo T-shirt", "25.00", title="M / Black", sku="TS-M-BLK"),
        12: FakeShopify.variant("Coffee Mug", "12.50", sku="MUG-1"),
        13: FakeShopify.variant("Limited Hoodie", "60.00", available=False),
        14: FakeShopify.variant("Euro Poster", "9.00", currency="EUR"),
    }
    return shopify


def cart(*lines, token="cart_abc"):
    return {"cart_token": token, "items": [{"variant_id": vid, "quantity": qty} for vid, qty in lines]}


def post(h, body, origin=STORE):
    return h.client.post("/api/shopify/checkout", json=body, headers={"Origin": origin})


class TestCreatingACheckout:
    def test_prices_come_from_shopify_and_a_checkout_link_is_returned(self, h, connected):
        response = post(h, cart((11, 2), (12, 1)))
        assert response.status_code == 200
        url = response.json()["checkout_url"]
        assert url.startswith("http://testserver/checkout?session=cs_")

        session = h.client.get(f"/api/v1/checkout/sessions/{url.split('=')[1]}", headers=h.store).json()
        assert session["currency"] == "USD" and session["subtotal"] == 6250  # 2 x 25.00 + 12.50
        assert [(i["name"], i["unit_amount"], i["quantity"]) for i in session["items"]] == [
            ("Logo T-shirt — M / Black", 2500, 2),
            ("Coffee Mug", 1250, 1),
        ]
        assert session["items"][0]["sku"] == "TS-M-BLK" and session["items"][0]["description"] == "M / Black"
        assert session["items"][1]["description"] == ""  # "Default Title" variants have no description
        assert session["items"][0]["image"] == "https://cdn.shopify.test/p.png"
        assert session["external_ref"] == "shopify:cart_abc" and session["metadata"] == {"source": "shopify"}
        assert session["success_url"] == STORE and session["cancel_url"] == f"{STORE}/cart"

    def test_prices_sent_by_the_browser_are_ignored(self, h, connected):
        body = cart((11, 1))
        body["items"][0].update({"unit_amount": 1, "price": 1, "name": "Free shirt"})
        body["total"] = 1
        session_id = post(h, body).json()["checkout_url"].split("=")[1]
        session = h.client.get(f"/api/v1/checkout/sessions/{session_id}", headers=h.store).json()
        assert session["subtotal"] == 2500 and session["items"][0]["name"] == "Logo T-shirt — M / Black"

    def test_the_same_variant_on_two_lines_is_merged(self, h, connected):
        session_id = post(h, cart((12, 1), (12, 2))).json()["checkout_url"].split("=")[1]
        items = h.client.get(f"/api/v1/checkout/sessions/{session_id}", headers=h.store).json()["items"]
        assert [(i["quantity"], i["unit_amount"]) for i in items] == [(3, 1250)]

    def test_shopify_is_asked_with_the_storefront_token(self, h, connected):
        post(h, cart((12, 1)))
        request = connected.requests[-1]
        assert request["token"] == FakeShopify.TOKEN and request["path"].endswith("/graphql.json")
        assert request["body"]["variables"]["ids"] == ["gid://shopify/ProductVariant/12"]

    def test_the_customer_can_place_the_order_on_the_resulting_checkout(self, h, connected):
        session_id = post(h, cart((11, 1))).json()["checkout_url"].split("=")[1]
        order = h.complete(session_id, "interac").json()
        assert order["order_number"] == 1001 and "$25.00" in order["payment_instructions"]
        assert h.order(1001)["external_ref"] == "shopify:cart_abc"


class TestRejectedCarts:
    def test_unknown_variant(self, h, connected):
        response = post(h, cart((999, 1)))
        assert response.status_code == 400 and "no longer available" in response.json()["error"]

    def test_out_of_stock_variant_is_named(self, h, connected):
        response = post(h, cart((12, 1), (13, 1)))
        assert response.status_code == 400 and "Limited Hoodie" in response.json()["error"]

    def test_mixed_currencies(self, h, connected):
        response = post(h, cart((12, 1), (14, 1)))
        assert response.status_code == 400 and "currenc" in response.json()["error"]

    @pytest.mark.parametrize(
        "body",
        [
            {"items": []},
            {"items": [{"variant_id": 0, "quantity": 1}]},
            {"items": [{"variant_id": 12, "quantity": 0}]},
            {"items": [{"variant_id": 12, "quantity": 1000}]},
            {"items": [{"variant_id": "abc", "quantity": 1}]},
            {"items": [{"variant_id": i, "quantity": 1} for i in range(1, 52)]},
            {},
        ],
    )
    def test_malformed_carts_are_rejected(self, h, connected, body):
        assert post(h, body).status_code == 400


class TestWhenShopifyIsNotReady:
    def test_not_connected(self, h, shopify):
        h.configure(storeUrl=STORE)
        response = post(h, cart((12, 1)), origin=STORE)
        assert response.status_code == 400 and "isn't connected" in response.json()["error"]

    def test_store_website_is_required(self, h, shopify):
        h.configure(shopifyDomain="my-shop.myshopify.com", shopifyStorefrontToken=FakeShopify.TOKEN)
        response = post(h, cart((12, 1)))
        assert response.status_code == 400 and "Store website" in response.json()["error"]

    def test_wrong_token_is_reported_clearly(self, h, connected):
        h.configure(shopifyStorefrontToken="wrong")
        response = post(h, cart((12, 1)))
        assert response.status_code == 502 and "rejected the Storefront access token" in response.json()["error"]

    def test_shopify_outage(self, h, connected):
        connected.force_status = 503
        response = post(h, cart((12, 1)))
        assert response.status_code == 502 and "Shopify" in response.json()["error"]

    def test_unreachable_shopify(self, h, connected, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "shopify_api_base_url", "http://127.0.0.1:9")
        response = post(h, cart((12, 1)))
        assert response.status_code == 502 and "Could not reach Shopify" in response.json()["error"]


class TestBrowserAccess:
    def test_the_storefront_origin_may_read_responses(self, h, connected):
        response = post(h, cart((12, 1)), origin=STORE)
        assert response.headers["access-control-allow-origin"] == STORE and "Origin" in response.headers["vary"]

    def test_www_and_the_myshopify_domain_are_allowed_too(self, h, connected):
        for origin in ("https://www.shop.example", "https://my-shop.myshopify.com"):
            assert post(h, cart((12, 1)), origin=origin).headers["access-control-allow-origin"] == origin

    def test_other_origins_get_no_cors_headers_even_on_errors(self, h, connected):
        ok = post(h, cart((12, 1)), origin="https://evil.example")
        bad = post(h, cart((999, 1)), origin="https://evil.example")
        assert "access-control-allow-origin" not in ok.headers and "access-control-allow-origin" not in bad.headers

    def test_errors_carry_cors_headers_so_the_theme_can_show_the_message(self, h, connected):
        response = post(h, cart((13, 1)), origin=STORE)
        assert response.status_code == 400 and response.headers["access-control-allow-origin"] == STORE

    def test_preflight(self, h, connected):
        allowed = h.client.options(
            "/api/shopify/checkout", headers={"Origin": STORE, "Access-Control-Request-Method": "POST"}
        )
        assert allowed.status_code == 204
        assert (
            allowed.headers["access-control-allow-origin"] == STORE
            and "POST" in allowed.headers["access-control-allow-methods"]
        )
        denied = h.client.options("/api/shopify/checkout", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in denied.headers

    def test_requests_are_rate_limited_per_client(self, h, connected, monkeypatch):
        monkeypatch.setattr(shopify_limiter, "max_events", 3)
        statuses = [post(h, cart((12, 1))).status_code for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]


class TestAdminSetup:
    def test_test_connection_returns_the_shop_name(self, h, connected):
        response = h.client.post("/api/admin/shopify/test", headers=h.admin)
        assert response.status_code == 200 and response.json() == {"ok": True, "shop_name": "Fake Shop"}

    def test_test_connection_with_a_bad_token(self, h, connected):
        h.configure(shopifyStorefrontToken="nope")
        assert h.client.post("/api/admin/shopify/test", headers=h.admin).status_code == 502

    def test_test_connection_needs_credentials_and_an_admin(self, h, shopify):
        assert h.client.post("/api/admin/shopify/test", headers=h.admin).status_code == 400
        assert h.client.post("/api/admin/shopify/test").status_code == 401

    def test_shop_domain_is_cleaned_and_validated(self, h):
        h.configure(shopifyDomain="https://My-Shop.myshopify.com/")
        assert h.client.get("/api/admin/settings", headers=h.admin).json()["shopifyDomain"] == "my-shop.myshopify.com"
        bad = h.client.put("/api/admin/settings", headers=h.admin, json={"shopifyDomain": "not a domain!"})
        assert bad.status_code == 400
