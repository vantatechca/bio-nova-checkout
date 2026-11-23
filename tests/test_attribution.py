"""Ad attribution: UTM parameters and ad-click ids, carried from checkout session through to the order."""

from tests.support import FakeShopify

STORE = "https://shop.example"


class TestCapture:
    def test_store_api_attribution_copies_onto_the_order(self, h):
        session = h.create_session(
            attribution={
                "utm_source": "newsletter",
                "utm_medium": "email",
                "utm_campaign": "spring",
                "click_id": "abc123",
                "click_provider": "google",
            }
        )
        assert session["utm_campaign"] == "spring"
        r = h.complete(session["id"], "bank")
        assert r.status_code == 200, r.text
        order = h.order(r.json()["order_number"])
        assert order["utm_source"] == "newsletter" and order["utm_medium"] == "email"
        assert order["utm_campaign"] == "spring"
        assert order["click_provider"] == "google" and order["click_id"] == "abc123"

    def test_shopify_checkout_attribution_sets_session_columns(self, h, shopify):
        h.configure(storeUrl=STORE, shopifyDomain="my-shop.myshopify.com", shopifyStorefrontToken=FakeShopify.TOKEN)
        shopify.variants = {11: FakeShopify.variant("Logo T-shirt", "25.00")}
        body = {
            "cart_token": "c1",
            "items": [{"variant_id": 11, "quantity": 1}],
            "attribution": {"utm_campaign": "bf-sale", "ttclid": "tt-1"},
        }
        r = h.client.post("/api/shopify/checkout", json=body, headers={"Origin": STORE})
        assert r.status_code == 200, r.text
        session_id = r.json()["checkout_url"].split("=")[1]
        session = h.client.get(f"/api/v1/checkout/sessions/{session_id}", headers=h.store).json()
        assert session["utm_campaign"] == "bf-sale"
        assert session["click_provider"] == "tiktok" and session["click_id"] == "tt-1"

    def test_checkout_page_view_stamps_attribution_first_wins(self, h):
        session = h.create_session()
        sid = session["id"]
        h.client.get(f"/api/public/sessions/{sid}", params={"utm_campaign": "spring", "gclid": "g-1"})
        h.client.get(f"/api/public/sessions/{sid}", params={"utm_campaign": "summer", "gclid": "g-2"})
        order = h.order(h.complete(sid, "bank").json()["order_number"])
        assert order["utm_campaign"] == "spring"  # the first view wins, the second does not overwrite it
        assert order["click_provider"] == "google" and order["click_id"] == "g-1"

    def test_attribution_report_aggregates_by_campaign(self, h):
        s1 = h.create_session(attribution={"utm_campaign": "spring"})["id"]
        h.create_session(attribution={"utm_campaign": "spring"})  # viewed, never ordered
        s3 = h.create_session(attribution={"utm_campaign": "summer"})["id"]
        h.client.get(f"/api/public/sessions/{s1}")
        h.client.get(f"/api/public/sessions/{s3}")
        h.complete(s1, "test")
        h.complete(s3, "test")

        out = h.client.get("/api/admin/attribution", headers=h.admin, params={"days": 7}).json()
        by_campaign = {row["campaign"]: row for row in out["rows"]}
        assert by_campaign["spring"]["sessions"] == 2
        assert by_campaign["spring"]["viewed"] == 1
        assert by_campaign["spring"]["orders"] == 1
        assert by_campaign["spring"]["revenue"] == 5000
        assert by_campaign["summer"]["orders"] == 1

    def test_attribution_report_falls_back_to_the_click_network_when_theres_no_campaign_tag(self, h):
        # Google Ads auto-tagging sends only gclid, with no utm_campaign unless one is manually configured --
        # that traffic should still show up as attributed, not collapse into "(none)" alongside truly direct visits.
        h.create_session(attribution={"click_provider": "google", "click_id": "g-1"})
        h.create_session()  # genuinely no attribution at all

        out = h.client.get("/api/admin/attribution", headers=h.admin, params={"days": 7}).json()
        by_campaign = {row["campaign"]: row for row in out["rows"]}
        assert by_campaign["google (no campaign tag)"]["sessions"] == 1
        assert by_campaign["(none)"]["sessions"] == 1

    def test_orders_export_includes_attribution_columns(self, h):
        session = h.create_session(attribution={"utm_campaign": "spring"})
        h.complete(session["id"], "bank")
        r = h.client.get("/api/admin/orders/export", headers=h.admin)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        body = r.text
        assert "utm_campaign" in body.splitlines()[0]
        assert "spring" in body
