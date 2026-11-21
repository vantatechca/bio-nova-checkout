"""Checkout page-view tracking (privacy-light: a salted hash of IP + user agent, never the IP)."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import CheckoutSession, Visit
from app.models.types import utcnow
from app.repositories import SessionRepository, VisitRepository
from app.services.config import AppConfig

log = logging.getLogger(__name__)
DEDUPE_WINDOW = timedelta(minutes=10)  # reloads of the same session by the same visitor don't count


@dataclass(frozen=True)
class VisitContext:
    ip: str
    user_agent: str
    host: str  # our own host, so internal referrers are ignored
    referrer: str  # document.referrer as reported by the page


def device_of(user_agent: str) -> str:
    if re.search(r"bot|crawl|spider|preview", user_agent, re.I):
        return "bot"
    if re.search(r"ipad|tablet", user_agent, re.I):
        return "tablet"
    if re.search(r"mobi|android|iphone", user_agent, re.I):
        return "mobile"
    return "desktop"


def referrer_host(referrer: str, own_host: str) -> str:
    host = (urlparse(referrer).hostname or "") if referrer else ""
    return "" if host == own_host.split(":")[0] else host[:100]


def record_visit(db: Session, config: AppConfig, session: CheckoutSession, ctx: VisitContext) -> None:
    """Best effort: analytics must never break the checkout page, so failures are logged and swallowed."""
    device = device_of(ctx.user_agent)
    if device == "bot":
        return
    visitor = hashlib.sha256(f"{config.salt}{ctx.ip}{ctx.user_agent}".encode()).hexdigest()[:12]
    now = utcnow()
    try:
        with db.begin_nested():  # savepoint: a failure here must not poison the request transaction
            visits = VisitRepository(db)
            if visits.seen_since(session.id, visitor, now - DEDUPE_WINDOW):
                return
            visits.add(
                Visit(
                    store_id=session.store_id,
                    at=now,
                    session_id=session.id,
                    visitor=visitor,
                    device=device,
                    referrer=referrer_host(ctx.referrer, ctx.host),
                )
            )
            SessionRepository(db).mark_viewed(session.id, now)
    except Exception:
        log.exception("Could not record visit")
