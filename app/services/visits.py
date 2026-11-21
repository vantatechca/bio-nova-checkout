"""Checkout page-view tracking (privacy-light: ``visitor`` is always a salted hash, never the IP itself).

The IP is also kept subject to ``VISIT_IP_MODE`` (truncated by default -- see ``stored_ip``) and resolved to a
country/city/ASN via ``app.services.geoip``, for the Visits admin tab. Off by default would mean no IP is
stored at all; the default ("truncated") never stores more than a /24 (IPv4) or /48 (IPv6).
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CheckoutSession, Visit
from app.models.types import utcnow
from app.repositories import SessionRepository, VisitRepository
from app.services import geoip
from app.services.config import AppConfig

log = logging.getLogger(__name__)
DEDUPE_WINDOW = timedelta(minutes=10)  # reloads of the same session by the same visitor don't count


@dataclass(frozen=True)
class VisitContext:
    ip: str
    user_agent: str
    host: str  # our own host, so internal referrers are ignored
    referrer: str  # document.referrer as reported by the page
    visitor_id: str = ""  # the bvid cookie, when the browser already has one


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


def stored_ip(ip: str, mode: str) -> str:
    """The IP as it is persisted, per ``VISIT_IP_MODE``: nothing, a truncated prefix, or the full address."""
    if mode == "full":
        return ip[:45]
    if mode != "truncated":  # "off", or anything else unrecognised
        return ""
    if ":" in ip:  # IPv6: keep the first three hextets (/48)
        return ":".join(ip.split(":")[:3]) + "::"
    parts = ip.split(".")
    if len(parts) == 4:  # IPv4: zero the last octet (/24)
        return ".".join(parts[:3]) + ".0"
    return ""  # not a recognisable IP literal


def record_visit(db: Session, config: AppConfig, session: CheckoutSession, ctx: VisitContext) -> None:
    """Best effort: analytics must never break the checkout page, so failures are logged and swallowed."""
    device = device_of(ctx.user_agent)
    if device == "bot":
        return
    # The visitor hash always uses the full IP, regardless of VISIT_IP_MODE, so unique-visitor counts don't
    # change with it; a first-party cookie (once set) is used instead, since it survives an IP change. Either
    # way this is truncated to the column's width -- it only needs to be unique-enough, not reversible.
    visitor_source = ctx.visitor_id or hashlib.sha256(f"{config.salt}{ctx.ip}{ctx.user_agent}".encode()).hexdigest()
    visitor = visitor_source[:12]
    mode = get_settings().ip_mode
    geo = geoip.lookup(ctx.ip)
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
                    ip=stored_ip(ctx.ip, mode),
                    country=geo.country,
                    city=geo.city,
                    asn=geo.asn or None,
                    isp=geo.isp,
                )
            )
            SessionRepository(db).mark_viewed(session.id, now)
    except Exception:
        log.exception("Could not record visit")
