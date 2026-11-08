from concurrent.futures import ThreadPoolExecutor


class TestAdminTabs:
    def test_orders_land_in_the_right_tab(self, h):
        pending = h.place_order("bank")["number"]
        paid = h.place_order("test")["number"]
        cancelled = h.place_order("zelle")["number"]
        h.update_order(cancelled, status="cancelled", notify=False)
        failed_payment = h.place_order("bank")["number"]
        h.update_order(failed_payment, payment_status="failed")
        assert h.tab("pending") == [pending]
        assert h.tab("paid") == [paid]
        assert h.tab("failed") == sorted([cancelled, failed_payment])

    def test_refunded_orders_move_to_failed_tab_and_out_of_paid(self, h):
        number = h.place_order("test")["number"]
        assert h.tab("paid") == [number]
        h.update_order(number, status="refunded", payment_status="refunded")
        assert h.tab("paid") == [] and h.tab("failed") == [number]

    def test_stats_counts_match_tabs(self, h):
        h.place_order("bank"), h.place_order("test"), h.place_order("test")
        stats = h.client.get("/api/admin/stats", headers=h.admin).json()
        assert stats["counts"] == {"pending": 1, "paid": 2, "failed": 0}
        assert stats["total_orders"] == 3 and stats["paid_revenue"] == 10000

    def test_search_matches_number_name_email_and_reference(self, h):
        order = h.place_order("bank", external_ref="WOO-777")
        for q in (str(order["number"]), "lovelace", "ada@example", "WOO-777"):
            r = h.client.get("/api/admin/orders", headers=h.admin, params={"q": q})
            assert [o["number"] for o in r.json()["data"]] == [order["number"]], q

    def test_search_treats_percent_and_underscore_literally(self, h):
        h.place_order("bank")
        for q in ("%", "_"):
            assert h.client.get("/api/admin/orders", headers=h.admin, params={"q": q}).json()["data"] == []

    def test_status_filter_and_invalid_values(self, h):
        h.place_order("test")
        assert (
            len(h.client.get("/api/admin/orders", headers=h.admin, params={"status": "processing"}).json()["data"]) == 1
        )
        assert h.client.get("/api/admin/orders", headers=h.admin, params={"status": "bogus"}).status_code == 400


class TestUpdatingOrders:
    def test_marking_paid_records_reference_and_moves_to_processing(self, h):
        number = h.place_order("bank")["number"]
        order = h.update_order(number, payment_status="paid", payment_reference="CA-123")
        assert (order["status"], order["payment_status"], order["payment_reference"]) == (
            "processing",
            "paid",
            "CA-123",
        )
        assert order["paid_at"] is not None
        texts = [e["text"] for e in order["history"]]
        assert any("Payment: pending → paid" in t for t in texts) and any(
            "Payment reference: CA-123" in t for t in texts
        )

    def test_explicit_status_is_respected_when_marking_paid(self, h):
        number = h.place_order("bank")["number"]
        assert h.update_order(number, payment_status="paid", status="shipped")["status"] == "shipped"

    def test_noop_update_changes_nothing(self, h):
        number = h.place_order("bank")["number"]
        before = h.order(number)
        after = h.update_order(number, status="pending", notes="")
        assert after["updated_at"] == before["updated_at"] and len(after["history"]) == len(before["history"])

    def test_tracking_and_notes(self, h):
        number = h.place_order("bank")["number"]
        order = h.update_order(number, tracking_number="1Z999", notes="  call first  ", status="shipped")
        assert order["tracking_number"] == "1Z999" and order["notes"] == "call first" and order["status"] == "shipped"

    def test_invalid_status_is_rejected(self, h):
        number = h.place_order("bank")["number"]
        r = h.client.patch(f"/api/admin/orders/{number}", headers=h.admin, json={"status": "teleported"})
        assert r.status_code == 400 and "status" in r.json()["error"]

    def test_unknown_order_is_404(self, h):
        assert h.client.get("/api/admin/orders/9999", headers=h.admin).status_code == 404
        assert h.client.patch("/api/admin/orders/ord_nope", headers=h.admin, json={"notes": "x"}).status_code == 404

    def test_eight_simultaneous_mark_paid_requests_apply_once(self, h):
        number = h.place_order("bank")["number"]

        def mark_paid(_):
            return h.client.patch(
                f"/api/admin/orders/{number}",
                headers=h.admin,
                json={"payment_status": "paid", "payment_reference": "R"},
            )

        with ThreadPoolExecutor(8) as pool:
            assert {r.status_code for r in pool.map(mark_paid, range(8))} == {200}
        order = h.order(number)
        assert sum("Payment: pending → paid" in e["text"] for e in order["history"]) == 1
        webhook_events = h.sql("SELECT COUNT(*) FROM email_log WHERE type = 'paid'")[0][0]
        assert webhook_events == 1  # only one "payment received" email despite eight requests


class TestStoreApi:
    def test_order_lookup_by_number_id_and_reference(self, h):
        order = h.place_order("bank", external_ref="cart_55")
        by_number = h.client.get(f"/api/v1/orders/{order['number']}", headers=h.store).json()
        by_id = h.client.get(f"/api/v1/orders/{order['id']}", headers=h.store).json()
        listed = h.client.get("/api/v1/orders", headers=h.store, params={"external_ref": "cart_55"}).json()["data"]
        assert by_number["id"] == by_id["id"] == listed[0]["id"]
        assert h.client.get("/api/v1/orders", headers=h.store, params={"external_ref": "other"}).json()["data"] == []

    def test_store_can_mark_paid_and_skip_customer_email(self, h, smtp_server):
        h.configure_smtp(smtp_server)
        number = h.place_order("bank")["number"]
        h.run_worker()
        sent_before = len(smtp_server.mails)
        r = h.client.patch(
            f"/api/v1/orders/{number}", headers=h.store, json={"payment_status": "paid", "notify": False}
        )
        assert r.status_code == 200 and r.json()["payment_status"] == "paid"
        h.run_worker()
        assert len(smtp_server.mails) == sent_before  # notify:false suppressed the receipt


class TestCommitBeforeResponse:
    def test_a_failed_commit_is_reported_to_the_client_not_swallowed(self, h, monkeypatch):
        """The transaction must commit before the response is sent; otherwise a failed commit would
        still answer "200 OK" and the change would silently be lost."""
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.orm import Session

        number = h.place_order("bank")["number"]

        def failing_commit(self):
            raise OperationalError("COMMIT", {}, Exception("simulated database failure"))

        monkeypatch.setattr(Session, "commit", failing_commit)
        response = h.client.patch(f"/api/admin/orders/{number}", headers=h.admin, json={"payment_status": "paid"})
        monkeypatch.undo()

        assert response.status_code == 503 and response.json() == {"error": "Database unavailable, please retry"}
        assert h.order(number)["payment_status"] == "pending"  # nothing was half-applied
