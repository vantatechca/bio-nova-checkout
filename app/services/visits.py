"""Checkout page-view tracking (privacy-light: ``visitor`` is always a salted hash, never the IP itself).

The IP is also kept subject to ``VISIT_IP_MODE`` (truncated by default -- see ``stored_ip``) and resolved to a
country/city/ASN via ``app.services.geoip``, for the Visits admin tab. Off by default would mean no IP is
stored at all; the default ("truncated") never stores more than a /24 (IPv4) or /48 (IPv6).
"""

from __future__ import annotations

import functools
import hashlib
import ipaddress
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CheckoutSession, Visit
from app.models.types import utcnow
from app.repositories import SessionRepository, VisitRepository
from app.schemas.settings import StoreSettings
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
    headers: Mapping[str, str] = field(default_factory=dict)  # for the internal_header_name/value marker check


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


@functools.lru_cache(maxsize=64)
def _parsed_networks(ranges: tuple[str, ...]) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Parses (and caches) a config's CIDR list -- this runs on every page view and session creation, so it's
    worth not re-parsing the same strings on every single request. Keyed on the exact tuple of range strings,
    so a settings change (a new tuple) just parses once more; nothing here can go stale."""
    parsed = []
    for entry in ranges:
        try:
            parsed.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue  # validated at save time (_check_ip_ranges); a bad entry here just never matches
    return tuple(parsed)


def is_internal_ip(ip: str, ranges: list[str]) -> bool:
    """Whether ``ip`` falls in any of the configured internal/non-customer CIDR ranges (``StoreSettings
    .internal_ip_range_list``). An unparsable ``ip`` is "not internal", not an error worth breaking the
    checkout over."""
    if not ranges:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in network for network in _parsed_networks(tuple(ranges)))


def is_internal_request(ip: str, user_agent: str, headers: Mapping[str, str], settings: StoreSettings) -> bool:
    """Whether a request (visit, or a checkout session being created) should be treated as internal/non-customer
    traffic: its IP falls in a configured range, its User-Agent contains a configured marker substring, or it
    sends the configured marker header/value pair. Any one of the three is enough; none configured = never
    internal, so this is a strict opt-in, not a default-on filter."""
    if is_internal_ip(ip, settings.internal_ip_range_list):
        return True
    ua = user_agent.lower()
    if any(marker in ua for marker in settings.internal_user_agent_marker_list):
        return True
    if (
        settings.internal_header_name
        and settings.internal_header_value
        and headers.get(settings.internal_header_name) == settings.internal_header_value
    ):
        return True
    return False


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
    store = config.store_by_id(session.store_id)
    internal = is_internal_request(ctx.ip, ctx.user_agent, ctx.headers, store.settings) if store else False
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
                    is_internal=internal,
                )
            )
            SessionRepository(db).mark_viewed(session.id, now)
    except Exception:
        log.exception("Could not record visit")
