"""Email and webhook delivery through the transactional outbox."""

import hashlib
import hmac
import json


class TestEmails:
    def test_without_smtp_emails_are_logged_as_skipped(self, h):
        h.place_order("bank")
        rows = h.sql("SELECT status, error FROM email_log")
        assert rows and all(r[0] == "skipped" and r[1] == "SMTP not configured" for r in rows)
        assert h.run_worker() == 0

    def test_confirmation_with_payment_instructions_is_sent(self, h, smtp_server):
        h.configure_smtp(smtp_server)
        h.place_order("bank")
        assert h.run_worker() == 1
        mail = smtp_server.mails[0]
        assert mail.recipients == ["ada@example.com"] and mail.sender == "orders@shop.test"
        assert mail.subject == "Order #1001 received - My Store"
        assert "by bank transfer" in mail.body and "Order #1001" in mail.body and "$50.00" in mail.body

    def test_paid_shipped_and_cancelled_emails(self, h, smtp_server):
        h.configure_smtp(smtp_server)
        number = h.place_order("bank")["number"]
        h.update_order(number, payment_status="paid", payment_reference="CONF9")
        h.update_order(number, status="shipped", tracking_number="TRK1")
        h.update_order(number, status="cancelled")
        while h.run_worker():
            pass
        subjects = [m.subject for m in smtp_server.mails]
        assert "Payment received for order #1001 - My Store" in subjects
        assert "Order #1001 has shipped - My Store" in subjects
        assert "Order #1001 cancelled - My Store" in subjects
        paid_mail = next(m for m in smtp_server.mails if m.subject.startswith("Payment received"))
        assert "CONF9" in paid_mail.body
        assert "TRK1" in next(m for m in smtp_server.mails if "shipped" in m.subject).body

    def test_admin_gets_new_order_alert_and_toggles_are_respected(self, h, smtp_server):
        h.configure_smtp(smtp_server, admin_email="boss@shop.test")
        h.client.put("/api/admin/email", headers=h.admin, json={"notify": {"confirmation": False}})
        h.place_order("bank")
        h.run_worker()
        assert [m.recipients for m in smtp_server.mails] == [["boss@shop.test"]]
        assert smtp_server.mails[0].subject.startswith("New order #1001")

    def test_failed_delivery_is_retried_then_marked_failed(self, h, smtp_server):
        h.configure_smtp(smtp_server, password="wrong")
        h.place_order("bank")
        h.run_worker()
        email = h.sql("SELECT status, attempts, error FROM email_log")[0]
        assert email[0] == "queued" and email[1] == 1 and "535" in email[2]  # back-off scheduled
        assert h.run_worker() == 0  # not due yet
        for _ in range(2):
            h.make_everything_due()
            h.run_worker()
        status, attempts, _ = h.sql("SELECT status, attempts, error FROM email_log")[0]
        assert (status, attempts) == ("failed", 3)

    def test_manual_retry_after_fixing_credentials(self, h, smtp_server):
        h.configure_smtp(smtp_server, password="wrong")
        h.place_order("bank")
        h.run_worker()
        h.client.put("/api/admin/email", headers=h.admin, json={"smtp": {"pass": "secret"}})
        email_id = h.client.get("/api/admin/email", headers=h.admin).json()["log"][0]["id"]
        r = h.client.post(f"/api/admin/email/{email_id}/retry", headers=h.admin)
        assert r.json() == {"status": "sent", "error": None} and len(smtp_server.mails) == 1

    def test_test_email_endpoint(self, h, smtp_server):
        assert (
            h.client.post("/api/admin/email/test", headers=h.admin, json={"to": "me@x.co"}).status_code == 400
        )  # no SMTP yet
        h.configure_smtp(smtp_server)
        assert h.client.post("/api/admin/email/test", headers=h.admin, json={"to": "me@x.co"}).status_code == 200
        assert smtp_server.mails[0].recipients == ["me@x.co"]
        assert h.client.post("/api/admin/email/test", headers=h.admin, json={"to": "nope"}).status_code == 400

    def test_smtp_password_is_never_returned(self, h, smtp_server):
        h.configure_smtp(smtp_server)
        smtp = h.client.get("/api/admin/email", headers=h.admin).json()["settings"]["smtp"]
        assert smtp["pass"] == "" and smtp["passSet"] is True
        assert "secret" not in h.client.get("/api/admin/email", headers=h.admin).text


class TestWebhooks:
    def test_payload_is_signed_and_describes_the_order(self, h, webhook_receiver):
        h.configure(webhookUrl=webhook_receiver.url)
        secret = h.client.get("/api/admin/settings", headers=h.admin).json()["webhookSecret"]
        h.place_order("test", external_ref="cart_7")
        h.run_worker()
        events = [json.loads(r.body)["event"] for r in webhook_receiver.received]
        assert sorted(events) == ["order.created", "order.paid"]
        hook = webhook_receiver.received[0]
        expected = "sha256=" + hmac.new(secret.encode(), hook.body, hashlib.sha256).hexdigest()
        assert hook.headers["x-checkout-signature"] == expected
        data = json.loads(hook.body)["data"]
        assert data["number"] == 1001 and data["external_ref"] == "cart_7" and data["payment_status"] == "paid"

    def test_marking_paid_fires_updated_and_paid_events(self, h, webhook_receiver):
        h.configure(webhookUrl=webhook_receiver.url)
        number = h.place_order("bank")["number"]
        h.run_worker()
        webhook_receiver.received.clear()
        h.update_order(number, payment_status="paid")
        h.run_worker()
        assert sorted(json.loads(r.body)["event"] for r in webhook_receiver.received) == ["order.paid", "order.updated"]

    def test_failed_delivery_retries_with_identical_payload_then_succeeds(self, h, webhook_receiver):
        webhook_receiver.statuses = [500, 200]
        h.configure(webhookUrl=webhook_receiver.url)
        h.place_order("bank")
        h.run_worker()
        assert h.sql("SELECT state, http_status, attempts FROM webhook_deliveries")[0] == ("pending", 500, 1)
        h.make_everything_due()
        h.run_worker()
        assert h.sql("SELECT state, http_status, attempts FROM webhook_deliveries")[0] == ("delivered", 200, 2)
        assert webhook_receiver.received[0].body == webhook_receiver.received[1].body

    def test_gives_up_after_four_attempts(self, h, webhook_receiver):
        webhook_receiver.statuses = [503] * 10
        h.configure(webhookUrl=webhook_receiver.url)
        h.place_order("bank")
        for _ in range(5):
            h.make_everything_due()
            h.run_worker()
        assert h.sql("SELECT state, attempts FROM webhook_deliveries")[0] == ("failed", 4)

    def test_unreachable_receiver_records_the_error(self, h):
        h.configure(webhookUrl="http://127.0.0.1:9/hook")
        h.place_order("bank")
        h.run_worker()
        state, status, error = h.sql("SELECT state, http_status, error FROM webhook_deliveries")[0]
        assert state == "pending" and status is None and error

    def test_nothing_is_queued_without_a_webhook_url(self, h):
        h.place_order("bank")
        assert h.sql("SELECT COUNT(*) FROM webhook_deliveries")[0][0] == 0

    def test_deliveries_are_listed_in_settings(self, h, webhook_receiver):
        h.configure(webhookUrl=webhook_receiver.url)
        h.place_order("bank")
        h.run_worker()
        log = h.client.get("/api/admin/settings", headers=h.admin).json()["webhookLog"]
        assert log[0]["event"] == "order.created" and log[0]["status"] == 200 and log[0]["order"] == 1001
