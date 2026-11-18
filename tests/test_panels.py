"""Content panels: version history, safe publishing, the stealth 404 and content validation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.database import get_engine, session_scope
from app.models.types import utcnow
from app.repositories import PanelRepository
from app.security import panel_limiter
from app.services import panels
from app.services.panel_content import looks_like_full_card_number, passes_luhn

ADS = {"Authorization": "Bearer ads-secret-key"}
SITES = {"Authorization": "Bearer sites-secret-key"}
VISA = "4242 4242 4242 4242"


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ads_data_key", "ads-secret-key")
    monkeypatch.setattr(settings, "sites_key", "sites-secret-key")


class Bot:
    """Talks to one panel the way the integration does."""

    def __init__(self, client, panel: str = "ads", headers: dict | None = None) -> None:
        self.client, self.panel = client, panel
        self.headers = headers or (ADS if panel == "ads" else SITES)

    def url(self, section: str, tail: str = "") -> str:
        return f"/api/panels/{self.panel}/{section}{tail}"

    def put(self, section: str, headline: str = "x", **extra):
        return self.client.put(
            self.url(section), headers=self.headers, json={"content": {"headline": headline}, **extra}
        )

    def get(self, section: str):
        r = self.client.get(self.url(section), headers=self.headers)
        assert r.status_code == 200, r.text
        return r.json()

    def publish(self, section: str, visible: bool = True):
        return self.client.patch(self.url(section), headers=self.headers, json={"visible": visible})

    def delete(self, section: str):
        return self.client.delete(self.url(section), headers=self.headers)

    def versions(self, section: str) -> list[dict]:
        r = self.client.get(self.url(section, "/versions"), headers=self.headers)
        assert r.status_code == 200, r.text
        return r.json()

    def restore(self, section: str, version: int):
        return self.client.post(self.url(section, "/restore"), headers=self.headers, json={"version": version})


@pytest.fixture
def ads(client) -> Bot:
    return Bot(client, "ads")


@pytest.fixture
def sites(client) -> Bot:
    return Bot(client, "sites")


def execute(statement: str, **params) -> None:
    with get_engine().begin() as conn:
        conn.execute(text(statement), params)


def log_rows() -> int:
    with get_engine().connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM panel_log")).scalar_one()


# ================================================================ history, undo, soft delete, log
class TestVersionHistory:
    def test_versions_count_up_without_gaps(self, ads):
        for n in range(1, 5):
            assert ads.put("canva", f"v{n}").status_code == 200
        # The first write creates the section; every later one snapshots what it replaces.
        assert [v["version"] for v in ads.versions("canva")] == [3, 2, 1]

    def test_a_version_holds_what_was_live_before_the_next_change(self, ads):
        for n in range(1, 4):
            ads.put("canva", f"v{n}")
        for n in (1, 2):
            r = ads.client.get(ads.url("canva", f"/versions/{n}"), headers=ads.headers)
            assert r.json()["content"] == {"headline": f"v{n}"}

    def test_the_version_list_is_metadata_only(self, ads):
        ads.put("canva", "a")
        ads.put("canva", "b")
        (entry,) = ads.versions("canva")
        assert set(entry) == {"version", "action", "created_at"} and entry["action"] == "put"

    def test_deleting_hides_the_section_but_keeps_its_history(self, ads):
        ads.put("canva", "keep me")
        ads.publish("canva")
        assert ads.delete("canva").status_code == 200
        view = ads.get("canva")
        assert view["status"] == "coming_soon" and view["content"] is None and view["deleted"] is True
        assert [v["action"] for v in ads.versions("canva")] == ["delete", "patch"]

    def test_a_deleted_section_can_be_restored_and_comes_back_hidden(self, ads):
        ads.put("canva", "keep me")
        ads.publish("canva")
        ads.delete("canva")
        assert ads.restore("canva", 1).status_code == 200
        view = ads.get("canva")
        assert view["content"] == {"headline": "keep me"} and view["deleted"] is False and view["visible"] is False

    def test_restoring_is_itself_undoable(self, ads):
        ads.put("canva", "one")
        ads.put("canva", "two")  # version 1 = "one"
        before = len(ads.versions("canva"))
        assert ads.restore("canva", 1).json()["version"] == before + 1
        newest = ads.versions("canva")[0]
        assert newest["action"] == "restore"
        undo = ads.client.get(ads.url("canva", f"/versions/{newest['version']}"), headers=ads.headers).json()
        assert undo["content"] == {"headline": "two"}

    def test_restoring_an_unknown_version_is_a_404(self, ads):
        ads.put("canva", "one")
        assert ads.restore("canva", 99).status_code == 404

    def test_old_versions_go_only_when_both_beyond_the_newest_and_past_retention(self, ads):
        for n in range(1, 7):
            ads.put("canva", f"v{n}")  # snapshots 1..5
        execute("UPDATE panel_versions SET created_at = :t WHERE version = 1", t=utcnow() - timedelta(days=200))
        with session_scope() as db:
            panels._prune(PanelRepository(db), "ads", "canva", keep_count=2, keep_days=90)
        # 5 and 4 are the newest two; 3 and 2 are beyond them but still young; 1 is both beyond and old.
        assert [v["version"] for v in ads.versions("canva")] == [5, 4, 3, 2]

    def test_purge_removes_only_what_is_past_the_recovery_window(self, ads):
        for section in ("canva", "excel", "card_info"):
            ads.put(section, "x")
            ads.delete(section)
        now = utcnow()
        for section, age in (
            ("canva", timedelta(days=30, seconds=5)),
            ("excel", timedelta(days=30) - timedelta(seconds=30)),
        ):
            execute("UPDATE panel_items SET deleted_at = :t WHERE section = :s", t=now - age, s=section)
        with session_scope() as db:
            panels.purge_expired(db, now)
        remaining = {row[0] for row in get_engine().connect().execute(text("SELECT section FROM panel_items"))}
        assert remaining == {"excel", "card_info"}
        assert ads.versions("canva") == [] and len(ads.versions("excel")) == 1


class TestActivityLog:
    def log(self, bot: Bot) -> list[dict]:
        r = bot.client.get(f"/api/panels/{bot.panel}/log", headers=bot.headers)
        assert r.status_code == 200, r.text
        return r.json()["entries"]

    def test_the_log_route_is_not_swallowed_by_the_section_route(self, ads):
        r = ads.client.get("/api/panels/ads/log", headers=ads.headers)
        assert r.status_code == 200 and r.json() == {"entries": []}

    def test_writes_deletes_and_restores_are_recorded(self, ads):
        ads.put("canva", "a")
        ads.put("canva", "b")
        ads.publish("canva")
        ads.restore("canva", 1)
        ads.delete("canva")
        entries = self.log(ads)
        assert [e["action"] for e in entries] == ["delete", "restore", "patch", "put", "put"]
        assert {e["outcome"] for e in entries} == {"ok"}

    def test_each_key_sees_only_its_own_activity(self, ads, sites):
        ads.put("canva", "a")
        sites.put("gmb", "b")
        assert [e["section"] for e in self.log(ads)] == ["canva"]
        assert [e["section"] for e in self.log(sites)] == ["gmb"]

    def test_a_request_that_fails_is_still_logged(self, ads):
        r = ads.client.put(ads.url("canva"), headers=ads.headers, json={"content": {"headline": VISA}})
        assert r.status_code == 422
        ads.client.put(ads.url("canva"), headers=ads.headers, content=b"{not json")
        outcomes = [(e["action"], e["outcome"]) for e in self.log(ads)]
        assert outcomes == [("put", "rejected"), ("put", "rejected")]
        # and nothing was stored
        assert ads.get("canva")["status"] == "coming_soon"


# ================================================================ safe publishing
class TestSafePublish:
    def test_a_new_section_is_hidden_even_when_the_body_says_visible(self, ads):
        r = ads.put("canva", "hello", visible=True)
        assert r.status_code == 200 and r.json()["visible"] is False and r.json()["status"] == "hidden"

    def test_writing_to_a_hidden_section_replaces_it_directly(self, ads):
        ads.put("canva", "first")
        ads.put("canva", "second")
        view = ads.get("canva")
        assert view["content"] == {"headline": "second"} and view["pending"] is None

    def test_writing_to_a_live_section_stages_a_draft_and_leaves_what_is_live(self, ads):
        ads.put("canva", "live")
        ads.publish("canva")
        view = ads.put("canva", "draft", visible=True).json()
        assert view["visible"] is True
        assert view["content"] == {"headline": "live"} and view["pending"] == {"headline": "draft"}

    def test_publishing_promotes_the_draft(self, ads):
        ads.put("canva", "live")
        ads.publish("canva")
        ads.put("canva", "draft")
        view = ads.publish("canva").json()
        assert view["content"] == {"headline": "draft"} and view["pending"] is None and view["visible"] is True

    def test_hiding_a_live_section_keeps_a_waiting_draft(self, ads):
        ads.put("canva", "live")
        ads.publish("canva")
        ads.put("canva", "draft")
        view = ads.publish("canva", visible=False).json()
        assert view["visible"] is False and view["pending"] == {"headline": "draft"}

    def test_deleting_discards_a_waiting_draft(self, ads):
        ads.put("canva", "live")
        ads.publish("canva")
        ads.put("canva", "draft")
        ads.delete("canva")
        ads.restore("canva", 1)
        assert ads.get("canva")["pending"] is None

    def test_restoring_discards_a_waiting_draft(self, ads):
        ads.put("canva", "one")
        ads.put("canva", "two")
        ads.publish("canva")
        ads.put("canva", "draft")
        ads.restore("canva", 1)
        view = ads.get("canva")
        assert view["pending"] is None and view["visible"] is False

    def test_a_push_to_a_deleted_section_cannot_bring_it_back_live(self, ads):
        ads.put("canva", "live")
        ads.publish("canva")
        ads.delete("canva")
        view = ads.put("canva", "again").json()
        assert view["visible"] is False and view["status"] == "hidden" and view["content"] == {"headline": "again"}

    def test_publishing_something_that_was_never_pushed_is_a_404(self, ads):
        assert ads.publish("canva").status_code == 404

    def test_the_section_and_panel_views_show_the_pending_state(self, ads):
        ads.put("canva", "live")
        ads.publish("canva")
        ads.put("canva", "draft")
        overview = ads.client.get("/api/panels/ads", headers=ads.headers).json()
        assert [s["id"] for s in overview["sections"]] == ["canva", "excel", "card_info"]
        assert overview["sections"][0]["pending"] == {"headline": "draft"}
        assert overview["sections"][1]["status"] == "coming_soon"


# ================================================================ authentication: the stealth 404
def fingerprint(r) -> tuple:
    return (
        r.status_code,
        r.content,
        r.headers.get("content-type"),
        r.headers.get("content-length"),
        r.headers.get("cache-control"),
    )


class TestStealth404:
    def test_every_kind_of_failure_looks_exactly_like_a_missing_path(self, client):
        reference = fingerprint(client.get("/api/this/path/does/not/exist"))
        assert reference[0] == 404
        wrong_key = {"Authorization": "Bearer nope"}
        attempts = [
            client.get("/api/panels/ads/canva", headers=wrong_key),  # wrong key, real panel
            client.get("/api/panels/ads/canva"),  # no key at all
            client.get("/api/panels/nowhere/canva", headers=ADS),  # unknown panel
            client.get("/api/panels/ads/nowhere", headers=ADS),  # unknown section
            client.get("/api/panels/sites/gmb", headers=ADS),  # one panel's key on another
            client.post("/api/panels/ads/canva", headers=ADS, json={}),  # a method the route does not handle
            client.patch("/api/panels/ads", headers=ADS, json={}),
            client.put("/api/panels/ads/canva", headers=wrong_key, content=b"{not json"),  # junk body, wrong key
            client.put("/api/panels/ads/canva", headers=wrong_key, json={"content": {"x": 1}}),
            client.get("/api/panels/ads/canva/versions/abc", headers=wrong_key),
        ]
        for attempt in attempts:
            assert fingerprint(attempt) == reference, attempt.request.url

    def test_none_of_those_failures_is_logged(self, client):
        client.get("/api/panels/ads/canva", headers={"Authorization": "Bearer nope"})
        client.get("/api/panels/nowhere/canva", headers=ADS)
        client.get("/api/panels/ads/nowhere", headers=ADS)
        client.post("/api/panels/ads/canva", headers=ADS, json={})
        assert log_rows() == 0

    def test_a_panel_without_a_configured_key_is_off(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "sites_key", None)
        reference = fingerprint(client.get("/api/this/path/does/not/exist"))
        # even an empty key must not get in
        for headers in ({"Authorization": "Bearer "}, {}, SITES):
            assert fingerprint(client.get("/api/panels/sites/gmb", headers=headers)) == reference

    def test_an_address_outside_the_allowlist_gets_the_same_404(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "panel_allowed_ips", "203.0.113.7")
        reference = fingerprint(client.get("/api/this/path/does/not/exist"))
        assert fingerprint(client.get("/api/panels/ads/canva", headers=ADS)) == reference

    def test_callers_are_throttled_whatever_the_key(self, client, monkeypatch):
        monkeypatch.setattr(panel_limiter, "max_events", 3)
        for _ in range(3):
            assert client.get("/api/panels/ads/canva", headers={"Authorization": "Bearer nope"}).status_code == 404
        assert client.get("/api/panels/ads/canva", headers=ADS).status_code == 429

    def test_the_right_key_works_and_is_the_only_one_that_does(self, ads, sites):
        assert ads.client.get("/api/panels/ads", headers=ADS).status_code == 200
        assert ads.client.get("/api/panels/sites", headers=SITES).status_code == 200
        assert ads.client.get("/api/panels/ads", headers=SITES).status_code == 404


# ================================================================ content rules
class TestContent:
    def put(self, bot: Bot, section: str, content: dict):
        return bot.client.put(bot.url(section), headers=bot.headers, json={"content": content})

    def test_every_part_can_be_combined_in_one_section(self, sites):
        content = {
            "headline": "All good",
            "summary": "Everything is up.",
            "metrics": [{"label": "Uptime", "value": 99.9, "trend": "+0.1%", "hint": "30 days"}],
            "entries": [{"title": "Toronto", "city": "Toronto", "image_url": "https://img.test/a.png", "rating": 4.5}],
            "sites": [
                {"name": "shop", "url": "https://shop.test", "status": "up", "uptime_pct": 99.9, "response_ms": 120}
            ],
            "table": {"columns": ["Site", "Visits"], "rows": [["shop", 10], ["blog", "7"]]},
        }
        r = self.put(sites, "live_sites", content)
        assert r.status_code == 200, r.text
        stored = r.json()["content"]
        assert stored["metrics"][0]["value"] == "99.9" and stored["table"]["rows"][0] == ["shop", "10"]

    def test_sites_are_only_allowed_in_live_sites_and_cards_only_in_card_info(self, ads, sites):
        site = {"name": "shop"}
        assert self.put(sites, "gmb", {"sites": [site]}).status_code == 400
        assert self.put(sites, "live_sites", {"sites": [site]}).status_code == 200
        card = {"label": "Visa", "last4": "4242"}
        assert self.put(ads, "canva", {"cards": [card]}).status_code == 400
        assert self.put(ads, "card_info", {"cards": [card]}).status_code == 200

    def test_cards_take_four_digits_and_nothing_else(self, ads):
        for last4 in ("424", "42424", "abcd", "42 42"):
            r = self.put(ads, "card_info", {"cards": [{"label": "Visa", "last4": last4}]})
            assert r.status_code == 400, last4

    def test_a_full_card_number_is_rejected_anywhere_in_any_section(self, ads, sites):
        for bot, section, content in (
            (ads, "canva", {"headline": f"paid with {VISA}"}),
            (ads, "card_info", {"cards": [{"label": "Visa", "last4": "4242", "note": "4242-4242-4242-4242"}]}),
            (sites, "gmb", {"entries": [{"title": "x", "note": "5555555555554444"}]}),
            (sites, "seo_city", {"table": {"columns": ["a"], "rows": [["378282246310005"]]}}),
            (ads, "excel", {"metrics": [{"label": "n", "value": 4242424242424242}]}),
        ):
            r = self.put(bot, section, content)
            assert r.status_code == 422, (section, r.text)
            assert "card number" in r.json()["error"]

    def test_ordinary_numbers_are_not_mistaken_for_cards(self):
        assert passes_luhn("4242424242424242")
        for text_ in ("Order 1763481600000", "ROAS 3.42 on $18,240.50", "call 416-555-0199", "4242 4242 4242 4243"):
            assert not looks_like_full_card_number(text_), text_
        assert looks_like_full_card_number("Visa 4242 4242 4242 4242 expires 12/29")

    def test_the_shape_is_checked(self, ads, sites):
        bad = [
            (ads, "canva", {"headline": "x", "bogus": 1}),  # unknown field
            (ads, "canva", {"metrics": [{"label": "only a label"}]}),
            (ads, "canva", {"entries": [{"title": "x", "image_url": "javascript:alert(1)"}]}),
            (ads, "excel", {"table": {"columns": ["a", "b"], "rows": [["only one"]]}}),
            (sites, "gmb", {"entries": [{"title": "x", "rating": 9}]}),
            (sites, "live_sites", {"sites": [{"name": "x", "uptime_pct": 120}]}),
        ]
        for bot, section, content in bad:
            assert self.put(bot, section, content).status_code == 400, content

    def test_the_body_must_be_json_with_a_content_object(self, ads):
        assert ads.client.put(ads.url("canva"), headers=ADS, content=b"nope").status_code == 400
        assert ads.client.put(ads.url("canva"), headers=ADS, json=[1]).status_code == 400
        assert ads.client.put(ads.url("canva"), headers=ADS, json={}).status_code == 400
        assert ads.client.put(ads.url("canva"), headers=ADS, json={"content": {}, "extra": 1}).status_code == 400

    def test_oversized_bodies_are_refused(self, ads):
        r = ads.client.put(ads.url("canva"), headers=ADS, content=b"x" * (300 * 1024))
        assert r.status_code == 400 and "too large" in r.json()["error"]


# ================================================================ the admin page
class TestAdminDisplay:
    def test_the_page_needs_an_admin_token(self, client):
        assert client.get("/api/admin/panels/ads").status_code == 401
        assert client.get("/api/admin/panels/ads", headers=ADS).status_code == 401

    def test_unknown_panels_are_a_plain_404(self, h):
        assert h.client.get("/api/admin/panels/nope", headers=h.admin).status_code == 404

    def test_nothing_published_means_every_section_is_coming_soon(self, h):
        panel = h.client.get("/api/admin/panels/sites", headers=h.admin).json()
        assert [s["id"] for s in panel["sections"]] == ["live_sites", "gmb", "trustpilot", "seo_city", "reddit_city"]
        assert [s["tier"] for s in panel["sections"]] == ["included", "addon", "addon", "addon", "addon"]
        assert {s["status"] for s in panel["sections"]} == {"coming_soon"}

    def test_hidden_content_is_not_shown_and_live_content_is(self, h, sites):
        sites.put("gmb", "hidden for now")
        panel = h.client.get("/api/admin/panels/sites", headers=h.admin).json()
        assert next(s for s in panel["sections"] if s["id"] == "gmb")["content"] is None
        sites.publish("gmb")
        gmb = next(
            s for s in h.client.get("/api/admin/panels/sites", headers=h.admin).json()["sections"] if s["id"] == "gmb"
        )
        assert gmb["status"] == "live" and gmb["content"] == {"headline": "hidden for now"}

    def test_a_waiting_draft_leaves_no_trace_on_the_page(self, h, sites):
        sites.put("gmb", "live")
        sites.publish("gmb")
        sites.put("gmb", "draft")
        gmb = next(
            s for s in h.client.get("/api/admin/panels/sites", headers=h.admin).json()["sections"] if s["id"] == "gmb"
        )
        assert gmb["content"] == {"headline": "live"}
        # the page is what the customer sees: nothing about a draft, not even a hint that one exists
        assert set(gmb) == {"id", "title", "icon", "subtitle", "tier", "status", "content"}

    def test_content_is_shared_by_every_store(self, h, ads):
        ads.put("canva", "shared")
        ads.publish("canva")
        stores = h.client.get("/api/admin/stores", headers=h.admin).json()
        assert stores  # a store exists, and the panel call needs no store at all
        r = h.client.get("/api/admin/panels/ads", headers=h.admin)
        assert r.json()["sections"][0]["status"] == "live"

    def test_there_is_no_store_picker_in_the_ui(self, client):
        source = client.get("/static/admin/js/views/panels.js").text
        assert "store" not in source.lower().replace("storage", "")
