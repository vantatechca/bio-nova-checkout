"""The read-only analytics API (/api/v1/analytics/*): PII exclusion, pagination, and order lookup."""


class TestAnalyticsOrders:
    def analytics_headers(self, h) -> dict[str, str]:
        key = h.client.get("/api/admin/settings", headers=h.admin).json()["analyticsKey"]
        return {"Authorization": f"Bearer {key}"}

    def test_order_lookup_by_number_has_no_customer_pii(self, h):
        order = h.place_order("test")
        headers = self.analytics_headers(h)
        r = h.client.get(f"/api/v1/analytics/orders/{order['number']}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["number"] == order["number"] and body["session_id"] == order["session_id"]
        assert body["total"] == order["total"] and body["currency"] == order["currency"]
        for field in ("customer", "shipping_address", "order_ip", "notes", "tracking_number", "payment_reference"):
            assert field not in body, field

    def test_order_lookup_by_public_id_also_works(self, h):
        order = h.place_order("test")
        headers = self.analytics_headers(h)
        r = h.client.get(f"/api/v1/analytics/orders/{order['id']}", headers=headers)
        assert r.status_code == 200 and r.json()["number"] == order["number"]

    def test_unknown_order_is_a_404(self, h):
        headers = self.analytics_headers(h)
        assert h.client.get("/api/v1/analytics/orders/999999", headers=headers).status_code == 404

    def test_order_lookup_unlocks_the_session_timeline(self, h):
        order = h.place_order("test")
        headers = self.analytics_headers(h)
        session_id = h.client.get(f"/api/v1/analytics/orders/{order['number']}", headers=headers).json()["session_id"]
        r = h.client.get(f"/api/v1/analytics/sessions/{session_id}/timeline", headers=headers)
        assert r.status_code == 200 and len(r.json()) > 0


class TestAnalyticsAbandoned:
    def analytics_headers(self, h) -> dict[str, str]:
        key = h.client.get("/api/admin/settings", headers=h.admin).json()["analyticsKey"]
        return {"Authorization": f"Bearer {key}"}

    def test_abandoned_sessions_have_no_customer_name_or_email(self, h):
        h.create_session(customer={"name": "Ada Lovelace", "email": "ada@example.com"})
        h.sql("UPDATE checkout_sessions SET created_at = created_at - INTERVAL 1 DAY")
        headers = self.analytics_headers(h)
        r = h.client.get("/api/v1/analytics/abandoned", headers=headers, params={"hours": 1})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["rows"]) == 1
        assert "customer_name" not in body["rows"][0] and "customer_email" not in body["rows"][0]

    def test_pagination(self, h):
        for _ in range(3):
            h.create_session()
        h.sql("UPDATE checkout_sessions SET created_at = created_at - INTERVAL 1 DAY")
        headers = self.analytics_headers(h)
        page1 = h.client.get("/api/v1/analytics/abandoned", headers=headers, params={"hours": 1, "limit": 2}).json()
        assert len(page1["rows"]) == 2 and page1["has_more"] is True
        page2 = h.client.get(
            "/api/v1/analytics/abandoned", headers=headers, params={"hours": 1, "limit": 2, "offset": 2}
        ).json()
        assert len(page2["rows"]) == 1 and page2["has_more"] is False


class TestAnalyticsVisitsLookupPaging:
    def analytics_headers(self, h) -> dict[str, str]:
        key = h.client.get("/api/admin/settings", headers=h.admin).json()["analyticsKey"]
        return {"Authorization": f"Bearer {key}"}

    def test_limit_and_offset(self, h):
        for _ in range(3):
            h.client.get(f"/api/public/sessions/{h.create_session()['id']}")
        headers = self.analytics_headers(h)
        page1 = h.client.get("/api/v1/analytics/visits/lookup", headers=headers, params={"limit": 2}).json()
        page2 = h.client.get(
            "/api/v1/analytics/visits/lookup", headers=headers, params={"limit": 2, "offset": 2}
        ).json()
        assert len(page1) == 2 and len(page2) == 1
