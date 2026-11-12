from datetime import timedelta

from sqlalchemy import text

from app.database import get_engine
from app.models.types import utcnow

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120"}
PHONE = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17) Mobile/15E148"}


class TestRevenue:
    def test_totals_average_and_methods(self, h):
        h.place_order("test")
        paid_bank = h.place_order("bank")["number"]
        h.update_order(paid_bank, payment_status="paid")
        h.place_order("bank")  # still awaiting payment
        r = h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 7}).json()
        assert (r["today"], r["last7"], r["last30"], r["all_time"]) == (10000, 10000, 10000, 10000)
        assert (r["period_total"], r["period_orders"], r["avg_order"]) == (10000, 2, 5000)
        assert (r["awaiting_payment"], r["awaiting_count"]) == (5000, 1)
        assert len(r["daily"]) == 7 and r["daily"][-1]["amount"] == 10000 and r["daily"][-1]["orders"] == 2
        assert {m["label"]: m["amount"] for m in r["by_method"]} == {
            "Test payment (no real charge)": 5000,
            "Bank transfer": 5000,
        }

    def test_refunds_are_excluded_from_revenue(self, h):
        number = h.place_order("test")["number"]
        h.update_order(number, status="refunded", payment_status="refunded")
        r = h.client.get("/api/admin/revenue", headers=h.admin).json()
        assert r["all_time"] == 0 and (r["refunded"], r["refunded_count"]) == (5000, 1)

    def test_unpaid_orders_are_not_revenue(self, h):
        h.place_order("bank")
        assert h.client.get("/api/admin/revenue", headers=h.admin).json()["all_time"] == 0

    def test_other_currencies_are_excluded_and_counted(self, h):
        h.place_order("test", currency="EUR")
        r = h.client.get("/api/admin/revenue", headers=h.admin).json()
        assert r["all_time"] == 0 and r["excluded_other_currency"] == 1

    def test_orders_are_bucketed_by_the_admins_local_day(self, h):
        number = h.place_order("test")["number"]
        paid_at = utcnow().replace(hour=1, minute=0, second=0, microsecond=0)  # 01:00 UTC today
        with get_engine().begin() as conn:
            conn.execute(
                text("UPDATE orders SET paid_at = :t WHERE number = :n"),
                {"t": paid_at.replace(tzinfo=None), "n": number},
            )
        utc_view = h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 7, "tz": 0}).json()
        toronto = h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 7, "tz": 300}).json()  # UTC-5
        assert utc_view["daily"][-1]["amount"] == 5000
        assert (
            toronto["daily"][-1]["amount"] == 0 and toronto["daily"][-2]["amount"] == 5000
        )  # 01:00 UTC = previous evening

    def test_range_is_clamped_to_supported_values(self, h):
        assert h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 5}).json()["days"] == 30
        assert h.client.get("/api/admin/revenue", headers=h.admin, params={"tz": 5000}).status_code == 400


class TestVisits:
    def test_funnel_devices_and_referrers(self, h):
        viewed_and_ordered = h.create_session()["id"]
        viewed_only = h.create_session()["id"]
        h.create_session()  # never opened
        h.client.get(
            f"/api/public/sessions/{viewed_and_ordered}", params={"ref": "https://shop.test/cart"}, headers=PHONE
        )
        h.client.get(f"/api/public/sessions/{viewed_only}", headers=BROWSER)
        h.complete(viewed_and_ordered, "bank")
        v = h.client.get("/api/admin/visits", headers=h.admin, params={"days": 7}).json()
        assert (v["views"], v["visitors"]) == (2, 2)
        assert v["funnel"] == {"created": 3, "viewed": 2, "ordered": 1, "conversion": 50.0}
        assert {d["label"] for d in v["devices"]} == {"mobile", "desktop"}
        assert {r["label"] for r in v["referrers"]} == {"shop.test", "(direct / unknown)"}
        assert v["daily"][-1]["views"] == 2

    def test_reloads_within_ten_minutes_and_bots_are_ignored(self, h):
        sid = h.create_session()["id"]
        for _ in range(3):
            h.client.get(f"/api/public/sessions/{sid}", headers=BROWSER)
        h.client.get(f"/api/public/sessions/{sid}", headers={"User-Agent": "Googlebot/2.1"})
        assert h.client.get("/api/admin/visits", headers=h.admin).json()["views"] == 1

    def test_a_later_visit_counts_again(self, h):
        sid = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid}", headers=BROWSER)
        old = (utcnow() - timedelta(minutes=30)).replace(tzinfo=None)
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE visits SET at = :t"), {"t": old})
        h.client.get(f"/api/public/sessions/{sid}", headers=BROWSER)
        v = h.client.get("/api/admin/visits", headers=h.admin).json()
        assert v["views"] == 2 and v["visitors"] == 1

    def test_no_raw_ip_is_stored(self, h):
        sid = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid}", headers=BROWSER)
        visitor = h.sql("SELECT visitor FROM visits")[0][0]
        assert len(visitor) == 12 and "." not in visitor and "testclient" not in visitor
