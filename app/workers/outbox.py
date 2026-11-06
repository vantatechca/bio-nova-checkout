"""Background delivery of queued emails and webhooks.

Rows are claimed with ``SELECT ... FOR UPDATE SKIP LOCKED`` and given a lease, so several app
instances can run workers side by side, and a crash mid-delivery simply makes the row due again.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from app.database import session_scope
from app.models import EmailStatus
from app.models.types import utcnow
from app.repositories import OutboxRepository
from app.services import emails, webhooks
from app.services.config import config_service
from app.services.maintenance import purge_old_data

log = logging.getLogger(__name__)

LEASE = timedelta(minutes=5)
BATCH = 10
MAINTENANCE_EVERY = timedelta(hours=1)


class OutboxProcessor:
    """One pass over everything that is due. Kept separate from the thread so it is easy to test."""

    def run_once(self) -> int:
        return self._process_emails() + self._process_webhooks()

    def _process_emails(self) -> int:
        with session_scope() as db:
            smtp = config_service.get(db).email.smtp
            email_ids = [e.id for e in OutboxRepository(db).claim_due_emails(utcnow(), LEASE, BATCH)]
        for email_id in email_ids:
            # The network call happens outside the claim transaction so no row lock is held while sending.
            with session_scope() as db:
                email = OutboxRepository(db).get_email(email_id)
                if email is not None and email.status == EmailStatus.QUEUED:
                    emails.attempt_delivery(smtp, email)
        return len(email_ids)

    def _process_webhooks(self) -> int:
        with session_scope() as db:
            delivery_ids = [d.id for d in OutboxRepository(db).claim_due_webhooks(utcnow(), LEASE, BATCH)]
        for delivery_id in delivery_ids:
            with session_scope() as db:
                delivery = db.get(webhooks.WebhookDelivery, delivery_id)
                if delivery is not None:
                    webhooks.attempt_delivery(delivery)
        return len(delivery_ids)


class OutboxWorker(threading.Thread):
    def __init__(self, interval_seconds: float) -> None:
        super().__init__(name="outbox-worker", daemon=True)
        self.interval = interval_seconds
        self._stop_event = threading.Event()
        self._processor = OutboxProcessor()
        self._next_maintenance = utcnow()

    def run(self) -> None:
        log.info("Outbox worker started")
        while not self._stop_event.is_set():
            processed = 0
            try:
                processed = self._processor.run_once()
                if utcnow() >= self._next_maintenance:
                    with session_scope() as db:
                        purge_old_data(db)
                    self._next_maintenance = utcnow() + MAINTENANCE_EVERY
            except Exception:
                log.exception("Outbox worker iteration failed")
            self._stop_event.wait(0 if processed else self.interval)  # drain quickly while busy
        log.info("Outbox worker stopped")

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=10)
