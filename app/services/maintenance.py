"""Periodic housekeeping. Orders are never deleted."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.types import utcnow
from app.repositories import OutboxRepository, SessionRepository, VisitRepository

log = logging.getLogger(__name__)

ABANDONED_SESSION_DAYS = 7
VISIT_RETENTION_DAYS = 180
EMAIL_RETENTION_DAYS = 180
WEBHOOK_RETENTION_DAYS = 90


def purge_old_data(db: Session) -> None:
    now = utcnow()
    removed = SessionRepository(db).purge_abandoned(now - timedelta(days=ABANDONED_SESSION_DAYS))
    VisitRepository(db).purge(now - timedelta(days=VISIT_RETENTION_DAYS))
    OutboxRepository(db).purge(now - timedelta(days=EMAIL_RETENTION_DAYS), now - timedelta(days=WEBHOOK_RETENTION_DAYS))
    if removed:
        log.info("Purged %d abandoned checkout sessions", removed)
