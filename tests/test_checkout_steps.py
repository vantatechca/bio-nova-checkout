"""Checkout-form step milestones: a deeper funnel than just "viewed" / "ordered"."""


def step(h, session_id, name):
    return h.client.post(f"/api/public/sessions/{session_id}/steps", params={"step": name})


class TestSteps:
    def test_steps_in_order_show_in_the_funnel(self, h):
        session_id = h.create_session()["id"]
        for name in ("form_started", "contact_done", "address_done"):
            assert step(h, session_id, name).status_code == 204

        v = h.client.get("/api/admin/visits", headers=h.admin, params={"days": 7}).json()
        by_step = {s["label"]: s["count"] for s in v["funnel"]["steps"]}
        assert by_step["form_started"] == 1
        assert by_step["contact_done"] == 1
        assert by_step["address_done"] == 1
        assert by_step["method_chosen"] == 0
        assert by_step["pay_clicked"] == 0

    def test_a_duplicate_step_is_ignored_not_an_error(self, h):
        session_id = h.create_session()["id"]
        assert step(h, session_id, "form_started").status_code == 204
        assert step(h, session_id, "form_started").status_code == 204
        rows = h.sql("SELECT COUNT(*) FROM checkout_events WHERE session_id = :s", s=session_id)
        assert rows[0][0] == 1

    def test_an_unknown_step_is_rejected(self, h):
        session_id = h.create_session()["id"]
        assert step(h, session_id, "not_a_real_step").status_code == 400

    def test_steps_on_a_completed_session_are_not_recorded(self, h):
        session_id = h.create_session()["id"]
        h.complete(session_id, "bank")
        assert step(h, session_id, "form_started").status_code == 204
        rows = h.sql("SELECT COUNT(*) FROM checkout_events WHERE session_id = :s", s=session_id)
        assert rows[0][0] == 0

    def test_rate_limited_after_too_many_in_a_minute(self, h):
        session_id = h.create_session()["id"]
        for _ in range(60):
            step(h, session_id, "form_started")
        assert step(h, session_id, "form_started").status_code == 429
