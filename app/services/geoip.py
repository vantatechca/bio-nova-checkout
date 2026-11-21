"""IP geolocation via local MaxMind GeoLite2 databases.

Missing or unreadable database files degrade silently to empty results: geolocation is a nice-to-have for
analytics and fraud signals, and must never be able to break the checkout.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass

import geoip2.database
import geoip2.errors

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Geo:
    country: str = ""  # ISO-2
    city: str = ""
    asn: int = 0
    isp: str = ""


@functools.lru_cache
def _city_reader() -> geoip2.database.Reader | None:
    path = get_settings().geoip_city_db
    if not path:
        return None
    try:
        return geoip2.database.Reader(path)
    except Exception:
        log.warning("Could not open the GeoIP city database at %s", path)
        return None


@functools.lru_cache
def _asn_reader() -> geoip2.database.Reader | None:
    path = get_settings().geoip_asn_db
    if not path:
        return None
    try:
        return geoip2.database.Reader(path)
    except Exception:
        log.warning("Could not open the GeoIP ASN database at %s", path)
        return None


def lookup(ip: str) -> Geo:
    """Best effort: a missing database, or an IP the database can't resolve, just gives an empty field."""
    country = city = isp = ""
    asn = 0
    city_reader = _city_reader()
    if city_reader is not None:
        try:
            result = city_reader.city(ip)
            country = result.country.iso_code or ""
            city = result.city.name or ""
        except (geoip2.errors.AddressNotFoundError, ValueError):
            pass
    asn_reader = _asn_reader()
    if asn_reader is not None:
        try:
            result = asn_reader.asn(ip)
            asn = result.autonomous_system_number or 0
            isp = result.autonomous_system_organization or ""
        except (geoip2.errors.AddressNotFoundError, ValueError):
            pass
    return Geo(country=country[:2], city=city[:100], asn=asn, isp=isp[:200])
