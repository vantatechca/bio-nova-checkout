"""Downloads the MaxMind GeoLite2 databases at startup, if a license key is configured.

Best effort only: this must never stop the app from starting. If ``MAXMIND_LICENSE_KEY`` is unset, or a
database path is already configured explicitly, or the download/extraction fails for any reason, geo
enrichment simply stays off (as it already does with no configuration at all) -- see app.services.geoip.
"""

from __future__ import annotations

import io
import logging
import tarfile
import tempfile
from pathlib import Path

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "geoip"
EDITIONS = {"geoip_city_db": "GeoLite2-City", "geoip_asn_db": "GeoLite2-ASN"}
TIMEOUT_SECONDS = 60.0


def _download(edition_id: str, license_key: str) -> bytes | None:
    url = f"https://download.maxmind.com/app/geoip_download?edition_id={edition_id}&license_key={license_key}&suffix=tar.gz"
    try:
        response = httpx.get(url, timeout=TIMEOUT_SECONDS, follow_redirects=True)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        log.warning("Could not download %s from MaxMind: %s", edition_id, exc)
        return None


def _extract_mmdb(archive: bytes, edition_id: str, dest: Path) -> bool:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            member = next((m for m in tar.getmembers() if m.name.endswith(".mmdb")), None)
            if member is None:
                log.warning("No .mmdb file found in the %s download", edition_id)
                return False
            extracted = tar.extractfile(member)
            if extracted is None:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(extracted.read())
            return True
    except (tarfile.TarError, OSError):
        log.exception("Could not extract the %s database", edition_id)
        return False


def ensure_geoip_databases() -> None:
    """Fetches any missing GeoLite2 database whose path isn't already configured. Safe to call every startup:
    a database already present on disk (e.g. from an earlier boot of the same container) isn't re-downloaded."""
    settings = get_settings()
    license_key = settings.maxmind_license_key
    if not license_key:
        return
    for attr, edition_id in EDITIONS.items():
        if getattr(settings, attr):
            continue  # an explicit path was configured; respect it, don't override it
        dest = DOWNLOAD_DIR / f"{edition_id}.mmdb"
        if not dest.exists():
            archive = _download(edition_id, license_key)
            if archive is None or not _extract_mmdb(archive, edition_id, dest):
                continue
        setattr(settings, attr, str(dest))
        log.info("GeoLite2 database ready: %s -> %s", edition_id, dest)
