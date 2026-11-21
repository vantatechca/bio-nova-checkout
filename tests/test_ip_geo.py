"""IP truncation modes, GeoIP enrichment, the visitor cookie and the (informational-only) risk flags."""

import pytest

from app.config import get_settings
from app.services import geoip
from tests.helpers import ADDRESS


def fake_client_ip(monkeypatch, ip: str) -> None:
    """``request.client.host`` is fixed under TestClient, so the IP is faked where it's looked up."""
    monkeypatch.setattr("app.api.public.client_ip", lambda request: ip)


class TestIpMode:
    def test_truncated_mode_stores_a_24_prefix_never_the_full_ip(self, h, monkeypatch):
        fake_client_ip(monkeypatch, "203.0.113.42")
        sid = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid}")
        ip = h.sql("SELECT ip FROM visits")[0][0]
        assert ip == "203.0.113.0"
        assert "42" not in ip

    def test_full_mode_stores_the_whole_address(self, h, monkeypatch):
        monkeypatch.setattr(get_settings(), "visit_ip_mode", "full")
        fake_client_ip(monkeypatch, "203.0.113.42")
        sid = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid}")
        assert h.sql("SELECT ip FROM visits")[0][0] == "203.0.113.42"

    def test_off_mode_stores_nothing(self, h, monkeypatch):
        monkeypatch.setattr(get_settings(), "visit_ip_mode", "off")
        fake_client_ip(monkeypatch, "203.0.113.42")
        sid = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid}")
        assert h.sql("SELECT ip FROM visits")[0][0] == ""

    def test_visitor_hash_is_unaffected_by_ip_mode(self, h, monkeypatch):
        """The dedupe/uniqueness hash always uses the full IP, regardless of what gets stored."""
        monkeypatch.setattr(get_settings(), "visit_ip_mode", "off")
        fake_client_ip(monkeypatch, "203.0.113.42")
        sid = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid}")
        visitor = h.sql("SELECT visitor FROM visits")[0][0]
        assert len(visitor) == 12


class TestGeoip:
    def test_missing_database_files_give_no_crash_and_empty_values(self):
        assert geoip._city_reader() is None  # no GEOIP_CITY_DB configured in tests
        assert geoip.lookup("203.0.113.42") == geoip.Geo()

    def test_a_stubbed_lookup_fills_country_and_city_on_the_visit(self, h, monkeypatch):
        monkeypatch.setattr(
            geoip, "lookup", lambda ip: geoip.Geo(country="US", city="Columbus", asn=15169, isp="Google")
        )
        sid = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{sid}")
        country, city = h.sql("SELECT country, city FROM visits")[0]
        assert (country, city) == ("US", "Columbus")


class TestVisitorCookie:
    def test_the_cookie_is_set_once_and_reused(self, h):
        sid = h.create_session()["id"]
        first = h.client.get(f"/api/public/sessions/{sid}")
        cookie = first.cookies.get("bvid")
        assert cookie and len(cookie) == 32
        h.client.get(f"/api/public/sessions/{sid}")  # second view: no new cookie needed
        visitors = h.sql("SELECT DISTINCT visitor FROM visits")
        assert len(visitors) == 1


class TestRiskFlags:
    def test_country_mismatch_is_flagged_but_never_blocks(self, h, monkeypatch):
        monkeypatch.setattr(geoip, "lookup", lambda ip: geoip.Geo(country="US"))
        session_id = h.create_session()["id"]
        r = h.complete(session_id, "bank", shipping_address={**ADDRESS, "country": "Germany"})
        assert r.status_code == 200
        order = h.order(r.json()["order_number"])
        assert order["risk_flags"]["country_mismatch"] == "ip=US ship=DE"

    def test_matching_countries_are_not_flagged(self, h, monkeypatch):
        monkeypatch.setattr(geoip, "lookup", lambda ip: geoip.Geo(country="CA"))
        order = h.place_order("bank")  # tests/helpers.ADDRESS ships to Canada
        assert "country_mismatch" not in order["risk_flags"]

    def test_three_orders_from_one_ip_in_24h_trigger_velocity(self, h, monkeypatch):
        monkeypatch.setattr(get_settings(), "visit_ip_mode", "full")
        fake_client_ip(monkeypatch, "203.0.113.42")
        orders = [h.place_order("test") for _ in range(3)]
        assert "velocity" not in orders[0]["risk_flags"]
        assert "velocity" not in orders[1]["risk_flags"]
        assert orders[2]["risk_flags"]["velocity"] == "3 orders/24h from same ip"

    def test_a_datacenter_asn_is_flagged(self, h, monkeypatch):
        monkeypatch.setattr(get_settings(), "risk_datacenter_asns", "AS15169")
        monkeypatch.setattr(geoip, "lookup", lambda ip: geoip.Geo(asn=15169, isp="Google Cloud"))
        order = h.place_order("bank")
        assert order["risk_flags"]["datacenter"] == "Google Cloud"


class TestCompleteRateLimit:
    def test_rate_limited_after_checkout_rate_limit_calls(self, h, monkeypatch):
        from app.security import complete_limiter

        monkeypatch.setattr(complete_limiter, "max_events", 3)

        statuses = []
        for _ in range(4):
            sid = h.create_session()["id"]
            statuses.append(h.complete(sid, "bank").status_code)
        assert statuses[:3] == [200, 200, 200]
        assert statuses[3] == 429


@pytest.fixture(autouse=True)
def _geoip_cache_reset():
    """The city/ASN readers are ``lru_cache``d; a stale ``None`` from an earlier test must not leak forward."""
    geoip._city_reader.cache_clear()
    geoip._asn_reader.cache_clear()
    yield
    geoip._city_reader.cache_clear()
    geoip._asn_reader.cache_clear()
