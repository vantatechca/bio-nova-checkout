from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import DeliveryState, EmailLog, EmailStatus, WebhookDelivery

Row = TypeVar("Row", EmailLog, WebhookDelivery)


class OutboxRepository:
    """Emails and webhook deliveries waiting to be (re)sent."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- emails
    def add_email(self, email: EmailLog) -> None:
        self.db.add(email)
        self.db.flush()

    def get_email(self, email_id: str) -> EmailLog | None:
        return self.db.get(EmailLog, email_id)

    def recent_emails(self, limit: int = 100) -> list[EmailLog]:
        return list(self.db.scalars(select(EmailLog).order_by(EmailLog.created_at.desc()).limit(limit)))

    def email_stats(self, since: datetime) -> dict[str, int]:
        rows = self.db.execute(
            select(EmailLog.status, func.count()).where(EmailLog.created_at >= since).group_by(EmailLog.status)
        ).all()
        return {status: int(n) for status, n in rows}

    # ---- webhooks
    def add_webhook(self, delivery: WebhookDelivery) -> None:
        self.db.add(delivery)
        self.db.flush()

    def recent_webhooks(self, limit: int = 50) -> list[WebhookDelivery]:
        return list(self.db.scalars(select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(limit)))

    # ---- worker support
    def claim_due_emails(self, now: datetime, lease: timedelta, limit: int = 10) -> list[EmailLog]:
        stmt = (
            select(EmailLog)
            .where(EmailLog.status == EmailStatus.QUEUED, EmailLog.next_attempt_at <= now)
            .order_by(EmailLog.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(self.db.scalars(stmt))
        for row in rows:  # lease: if the worker dies mid-send, the row becomes due again later
            row.next_attempt_at = now + lease
        return rows

    def claim_due_webhooks(self, now: datetime, lease: timedelta, limit: int = 10) -> list[WebhookDelivery]:
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.state == DeliveryState.PENDING, WebhookDelivery.next_attempt_at <= now)
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(self.db.scalars(stmt))
        for row in rows:
            row.next_attempt_at = now + lease
        return rows

    # ---- retention
    def purge(self, emails_before: datetime, webhooks_before: datetime) -> None:
        self.db.execute(delete(EmailLog).where(EmailLog.created_at < emails_before))
        self.db.execute(delete(WebhookDelivery).where(WebhookDelivery.created_at < webhooks_before))
