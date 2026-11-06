"""Convenience wrapper so tests read like a story rather than a pile of HTTP calls."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import get_engine, session_scope
from app.models.types import utcnow
from app.workers.outbox import OutboxProcessor

ADDRESS = {"line1": "1 Main St", "city": "Toronto", "postal_code": "M5V 1A1", "country": "CA"}
CART = [{"name": "Shirt", "unit_amount": 2500, "quantity": 2}]


class Harness:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self._admin: dict[str, str] | None = None
        self._store: dict[str, str] | None = None

    # ---- auth
    @property
    def admin(self) -> dict[str, str]:
        if self._admin is None or not self._admin.get("Authorization"):
            token = self.client.post("/api/admin/login", json={"password": "test-admin-pw"}).json()["token"]
            self._admin = {"Authorization": f"Bearer {token}"}
        return self._admin

    @property
    def store(self) -> dict[str, str]:
        if self._store is None:
            key = self.client.get("/api/admin/settings", headers=self.admin).json()["apiKey"]
            self._store = {"Authorization": f"Bearer {key}"}
        return self._store

    # ---- admin settings
    def configure(self, **settings) -> None:
        r = self.client.put("/api/admin/settings", headers=self.admin, json=settings)
        assert r.status_code == 200, r.text

    def configure_smtp(self, server, *, password: str = "secret", admin_email: str = "") -> None:
        r = self.client.put(
            "/api/admin/email",
            headers=self.admin,
            json={
                "adminEmail": admin_email,
                "smtp": {
                    "host": "127.0.0.1",
                    "port": server.port,
                    "user": "mailer",
                    "pass": password,
                    "from": "Shop <orders@shop.test>",
                },
            },
        )
        assert r.status_code == 200, r.text

    # ---- checkout flow
    def create_session(self, items=None, **extra) -> dict:
        body = {"items": items or CART, "success_url": "https://shop.test/thanks", **extra}
        r = self.client.post("/api/v1/checkout/sessions", headers=self.store, json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def complete(self, session_id: str, method: str = "cod", **overrides):
        body = {
            "customer": {"name": "Ada Lovelace", "email": "ada@example.com"},
            "shipping_address": ADDRESS,
            "payment_method": method,
            **overrides,
        }
        return self.client.post(f"/api/public/sessions/{session_id}/complete", json=body)

    def place_order(self, method: str = "cod", items=None, **extra) -> dict:
        """Creates a session and places the order; returns the admin view of the order."""
        session = self.create_session(items, **extra)
        r = self.complete(session["id"], method)
        assert r.status_code == 200, r.text
        return self.order(r.json()["order_number"])

    def order(self, number: int) -> dict:
        r = self.client.get(f"/api/admin/orders/{number}", headers=self.admin)
        assert r.status_code == 200, r.text
        return r.json()

    def update_order(self, number: int, **fields) -> dict:
        r = self.client.patch(f"/api/admin/orders/{number}", headers=self.admin, json=fields)
        assert r.status_code == 200, r.text
        return r.json()

    def tab(self, name: str) -> list[int]:
        r = self.client.get("/api/admin/orders", headers=self.admin, params={"tab": name})
        assert r.status_code == 200, r.text
        return sorted(o["number"] for o in r.json()["data"])

    # ---- outbox
    @staticmethod
    def run_worker() -> int:
        return OutboxProcessor().run_once()

    @staticmethod
    def make_everything_due() -> None:
        """Skips the retry back-off so the worker will pick rows up again immediately."""
        past = (utcnow() - timedelta(seconds=1)).replace(tzinfo=None)
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE email_log SET next_attempt_at = :t WHERE status = 'queued'"), {"t": past})
            conn.execute(
                text("UPDATE webhook_deliveries SET next_attempt_at = :t WHERE state = 'pending'"), {"t": past}
            )

    @staticmethod
    def sql(statement: str, **params):
        with session_scope() as db:
            return db.execute(text(statement), params).all()
