"""Fraud/abuse signals attached to a placed order. Informational only -- these never block an order."""

from __future__ import annotations

from datetime import timedelta

import pycountry
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.types import utcnow
from app.repositories import OrderRepository
from app.schemas.checkout import AddressIn
from app.services import geoip
from app.services.visits import stored_ip

VELOCITY_WINDOW = timedelta(hours=24)
VELOCITY_THRESHOLD = 3


def _iso2(country_name: str) -> str:
    """The shipping address stores a country name (e.g. "United States"), geoip gives an ISO-2 code; this
    bridges the two. An unrecognised name is left alone rather than risk a false mismatch."""
    try:
        return pycountry.countries.lookup(country_name).alpha_2 if country_name else ""
    except LookupError:
        return ""


def evaluate(settings: Settings, ip: str, address: AddressIn, db: Session) -> dict[str, str]:
    """A flag name -> human-readable detail, for whichever signals fired. Never raises."""
    flags: dict[str, str] = {}
    geo = geoip.lookup(ip)

    ship_iso2 = _iso2(address.country)
    if geo.country and ship_iso2 and geo.country.upper() != ship_iso2.upper():
        flags["country_mismatch"] = f"ip={geo.country} ship={ship_iso2}"

    if geo.asn and f"AS{geo.asn}" in settings.risk_asn_set:
        flags["datacenter"] = geo.isp or str(geo.asn)

    # +1: this order itself hasn't been added yet, so "3 orders" means this one plus 2 earlier ones.
    count = OrderRepository(db).count_since(stored_ip(ip, settings.ip_mode), utcnow() - VELOCITY_WINDOW) + 1
    if count >= VELOCITY_THRESHOLD:
        flags["velocity"] = f"{count} orders/24h from same ip"

    return flags
