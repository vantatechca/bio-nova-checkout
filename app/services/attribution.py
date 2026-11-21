"""Normalises attribution data from a query string, and applies it to a session on a first-wins basis."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.schemas.checkout import CLICK_PROVIDERS, AttributionIn

UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


class _HasAttributionFields(Protocol):
    utm_source: str
    utm_medium: str
    utm_campaign: str
    utm_content: str
    utm_term: str
    click_provider: str
    click_id: str


def from_query_params(params: Mapping[str, str]) -> AttributionIn:
    """Reads ``utm_*`` and ad-click-id params from a query string. Only one click id is kept."""
    values = {field: params.get(field, "").strip()[:200] for field in UTM_FIELDS}
    click_provider = click_id = ""
    for key, provider in CLICK_PROVIDERS.items():
        value = params.get(key, "").strip()
        if value:
            click_provider, click_id = provider, value[:200]
            break
    return AttributionIn(**values, click_provider=click_provider, click_id=click_id)


def apply(target: _HasAttributionFields, attr: AttributionIn) -> None:
    """First-wins: a field already set (by an earlier view, or by the store at session creation) is left alone,
    so a session is never re-attributed by a later page view. Each field wins independently."""
    for field in (*UTM_FIELDS, "click_provider", "click_id"):
        if not getattr(target, field) and getattr(attr, field):
            setattr(target, field, getattr(attr, field))
