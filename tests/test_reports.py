from datetime import timedelta

from sqlalchemy import text

from app.database import get_engine
from app.models.types import utcnow

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120"}
PHONE = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17) Mobile/15E148"}
CART = [{"name": "Shirt", "unit_amount": 2500, "quantity": 2}]


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
        # 01:00 UTC on the most recent UTC day that has already reached that hour in Toronto's (UTC-5) calendar
        paid_at = (utcnow() - timedelta(hours=5)).replace(hour=1, minute=0, second=0, microsecond=0)
        with get_engine().begin() as conn:
            conn.execute(
                text("UPDATE orders SET paid_at = :t WHERE number = :n"),
                {"t": paid_at.replace(tzinfo=None), "n": number},
            )

        def amounts(tz):
            report = h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 7, "tz": tz}).json()
            return {d["date"]: d["amount"] for d in report["daily"]}

        utc_day = paid_at.date().isoformat()
        toronto_day = (paid_at - timedelta(hours=5)).date().isoformat()  # 01:00 UTC = the previous evening
        assert utc_day != toronto_day
        assert amounts(0)[utc_day] == 5000 and amounts(0).get(toronto_day, 0) == 0
        assert amounts(300)[toronto_day] == 5000 and amounts(300).get(utc_day, 0) == 0

    def test_any_reasonable_day_count_is_honoured_exactly(self, h):
        # Used to silently become 30 for anything outside {7, 30, 90}; now an exact window is actually computed.
        assert h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 5}).json()["days"] == 5
        assert h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 365}).json()["days"] == 365
        assert h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 0}).status_code == 422
        assert h.client.get("/api/admin/revenue", headers=h.admin, params={"days": 367}).status_code == 422
        assert h.client.get("/api/admin/revenue", headers=h.admin, params={"tz": 5000}).status_code == 400

    def test_an_exact_date_range_can_be_requested_instead_of_days(self, h):
        order = h.place_order("test")
        h.sql(f"UPDATE orders SET paid_at = '2026-11-18 15:00:00' WHERE number = {order['number']}")
        report = h.client.get(
            "/api/admin/revenue", headers=h.admin, params={"date_from": "2026-11-17", "date_to": "2026-11-19"}
        ).json()
        assert report["days"] == 3 and len(report["daily"]) == 3
        assert report["daily"][1]["date"] == "2026-11-18" and report["daily"][1]["amount"] == order["total"]
        assert sum(d["amount"] for d in report["daily"]) == order["total"]
        # outside the window: the order doesn't show up
        report2 = h.client.get(
            "/api/admin/revenue", headers=h.admin, params={"date_from": "2026-11-01", "date_to": "2026-11-10"}
        ).json()
        assert sum(d["amount"] for d in report2["daily"]) == 0

    def test_date_range_validation(self, h):
        assert (
            h.client.get("/api/admin/revenue", headers=h.admin, params={"date_from": "2026-11-19"}).status_code == 400
        )
        assert (
            h.client.get(
                "/api/admin/revenue", headers=h.admin, params={"date_from": "2026-11-19", "date_to": "2026-11-01"}
            ).status_code
            == 400
        )
        assert (
            h.client.get(
                "/api/admin/revenue", headers=h.admin, params={"date_from": "not-a-date", "date_to": "2026-11-01"}
            ).status_code
            == 422
        )


class TestVisits:
    def test_funnel_devices_and_referrers(self, h):
        viewed_and_ordered = h.create_session()["id"]
        viewed_only = h.create_session()["id"]
        h.create_session()  # never opened
        h.client.get(
            f"/api/public/sessions/{viewed_and_ordered}", params={"ref": "https://shop.test/cart"}, headers=PHONE
        )
        h.client.cookies.clear()  # a different visitor: without this they'd share the first one's bvid cookie
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

    def test_internal_user_agent_marker_flags_visit_without_hiding_it(self, h):
        h.configure(internalUserAgentMarkers="qa-tester-bot")
        normal = h.create_session()["id"]
        flagged = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{normal}", headers=BROWSER)
        h.client.cookies.clear()
        h.client.get(f"/api/public/sessions/{flagged}", headers={"User-Agent": "Mozilla/5.0 qa-tester-bot/1.0"})

        v = h.client.get("/api/admin/visits", headers=h.admin).json()
        assert (v["views"], v["visitors"]) == (2, 2)  # the flagged visit is still in the raw totals
        assert (v["views_excluding_internal"], v["visitors_excluding_internal"]) == (1, 1)

        rows = h.client.get("/api/admin/visits/lookup", headers=h.admin).json()
        assert {r["is_internal"] for r in rows} == {True, False}

    def test_internal_header_marker_requires_both_name_and_value(self, h):
        h.configure(internalHeaderName="X-Test-Client", internalHeaderValue="carl")
        sid = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid}", headers={**BROWSER, "X-Test-Client": "someone-else"})
        assert h.client.get("/api/admin/visits", headers=h.admin).json()["visitors_excluding_internal"] == 1

        h.client.cookies.clear()
        sid2 = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid2}", headers={**BROWSER, "X-Test-Client": "carl"})
        assert h.client.get("/api/admin/visits", headers=h.admin).json()["visitors_excluding_internal"] == 1

    def test_arrivals_report_breaks_down_by_campaign_term_click_device_and_city(self, h):
        h.configure(internalUserAgentMarkers="qa-tester-bot")
        tagged = h.create_session(
            attribution={
                "utm_campaign": "TEST-X2",
                "utm_term": "running shoes",
                "click_provider": "google",
                "click_id": "abc",
            }
        )
        h.client.get(f"/api/public/sessions/{tagged['id']}", headers=BROWSER)
        # A reload within 10 minutes must not add a second arrival.
        h.client.get(f"/api/public/sessions/{tagged['id']}", headers=BROWSER)
        h.client.cookies.clear()
        # An internal visit to the same tagged session: still a real visit, just excluded from this KPI report.
        h.client.get(f"/api/public/sessions/{tagged['id']}", headers={"User-Agent": "Mozilla/5.0 qa-tester-bot/1.0"})

        store_id = h.client.get("/api/admin/settings", headers=h.admin).json()["storeId"]
        today = utcnow().date().isoformat()  # tz=0 (default) means the local day is just the UTC day
        report = h.client.get("/api/admin/arrivals", headers=h.admin, params={"days": 7}).json()
        assert report["rows"] == [
            {
                "date": today,
                "store_id": store_id,
                "utm_campaign": "TEST-X2",
                "utm_term": "running shoes",
                "has_click_id": True,
                "device": "desktop",
                "city": "",
                "arrivals": 1,
                "views": 1,
            }
        ]
        # The internal visit is still a real, visible visit -- just not counted in this KPI breakdown.
        all_visits = h.client.get("/api/admin/visits", headers=h.admin, params={"days": 7}).json()
        assert all_visits["views"] == 2 and all_visits["views_excluding_internal"] == 1

    def test_arrivals_days_window_changes_the_total(self, h):
        sid = h.create_session(attribution={"utm_campaign": "TEST-X2"})["id"]
        h.client.get(f"/api/public/sessions/{sid}", headers=BROWSER)
        old = (utcnow() - timedelta(days=10)).replace(tzinfo=None)
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE visits SET at = :t"), {"t": old})

        def arrivals_total(days):
            rows = h.client.get("/api/admin/arrivals", headers=h.admin, params={"days": days}).json()["rows"]
            return sum(r["arrivals"] for r in rows)

        assert arrivals_total(7) == 0
        assert arrivals_total(30) == 1

    def test_sessions_vs_arrivals_counts_pressed_checkout_vs_opened(self, h):
        h.create_session(attribution={"utm_campaign": "TEST-X2"})  # pressed checkout, never opened
        opened = h.create_session(attribution={"utm_campaign": "TEST-X2"})["id"]
        h.client.get(f"/api/public/sessions/{opened}", headers=BROWSER)

        rows = h.client.get("/api/admin/arrivals", headers=h.admin, params={"days": 7}).json()["sessions_vs_arrivals"]
        row = next(r for r in rows if r["utm_campaign"] == "TEST-X2")
        assert (row["sessions_created"], row["arrived"]) == (2, 1)

    def test_internal_session_never_viewed_is_excluded_from_created_but_not_deleted(self, h):
        h.configure(internalUserAgentMarkers="qa-tester-bot")
        tester_marker = {"User-Agent": "Mozilla/5.0 qa-tester-bot/1.0"}
        # Flagged at creation time (the store-to-store call), never opened -- should drop out of "created".
        never_viewed = h.client.post(
            "/api/v1/checkout/sessions",
            headers={**h.store, **tester_marker},
            json={"items": CART, "success_url": "https://shop.test/thanks"},
        ).json()["id"]
        # Flagged at creation time, but opened -- counts in "created" and "viewed".
        viewed = h.client.post(
            "/api/v1/checkout/sessions",
            headers={**h.store, **tester_marker},
            json={"items": CART, "success_url": "https://shop.test/thanks"},
        ).json()["id"]
        h.client.get(f"/api/public/sessions/{viewed}", headers=BROWSER)
        # A normal session, for a baseline.
        h.create_session()

        funnel = h.client.get("/api/admin/visits", headers=h.admin).json()["funnel"]
        assert funnel["created"] == 2  # 3 sessions total, minus the never-viewed internal one
        assert funnel["viewed"] == 1

        # The never-viewed session row itself still exists -- excluded from one count, not deleted.
        ids = {row[0] for row in h.sql("SELECT id FROM checkout_sessions")}
        assert never_viewed in ids
