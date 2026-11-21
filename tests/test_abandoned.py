"""Abandoned checkout sessions: carts opened but never finished, and their activity timeline."""

from datetime import timedelta

from sqlalchemy import text

from app.database import get_engine
from app.models.types import utcnow


def age_session(session_id: str, hours: float) -> None:
    old = (utcnow() - timedelta(hours=hours)).replace(tzinfo=None)
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE checkout_sessions SET created_at = :t WHERE id = :id"), {"t": old, "id": session_id})


class TestAbandoned:
    def test_an_old_open_session_is_abandoned_a_fresh_one_is_not(self, h):
        old_id = h.create_session()["id"]
        age_session(old_id, hours=8)
        fresh_id = h.create_session()["id"]

        out = h.client.get("/api/admin/sessions/abandoned", headers=h.admin, params={"hours": 6}).json()
        ids = {row["id"] for row in out["rows"]}
        assert old_id in ids and fresh_id not in ids

    def test_a_completed_session_never_shows_as_abandoned(self, h):
        session_id = h.create_session()["id"]
        age_session(session_id, hours=8)
        h.complete(session_id, "bank")

        out = h.client.get("/api/admin/sessions/abandoned", headers=h.admin, params={"hours": 6}).json()
        assert session_id not in {row["id"] for row in out["rows"]}

    def test_abandoned_rows_show_how_far_the_customer_got(self, h):
        session_id = h.create_session()["id"]
        h.client.post(f"/api/public/sessions/{session_id}/steps", params={"step": "form_started"})
        h.client.post(f"/api/public/sessions/{session_id}/steps", params={"step": "address_done"})
        age_session(session_id, hours=8)

        out = h.client.get("/api/admin/sessions/abandoned", headers=h.admin, params={"hours": 6}).json()
        row = next(r for r in out["rows"] if r["id"] == session_id)
        assert set(row["steps"]) == {"form_started", "address_done"}


class TestTimeline:
    def test_timeline_merges_visits_steps_and_order_history(self, h):
        session_id = h.create_session()["id"]
        h.client.get(f"/api/public/sessions/{session_id}")
        h.client.post(f"/api/public/sessions/{session_id}/steps", params={"step": "form_started"})
        h.complete(session_id, "bank")

        items = h.client.get(f"/api/admin/sessions/{session_id}/timeline", headers=h.admin).json()
        timestamps = [it["at"] for it in items]
        assert timestamps == sorted(timestamps)  # chronological
        kinds = {it["kind"] for it in items}
        assert {"session", "visit", "step", "order"} <= kinds
