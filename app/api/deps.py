"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import NotFound, Unauthorized
from app.security import AdminTokens, bearer_token
from app.services.config import AppConfig, StoreRecord, config_service

# scope="function": the transaction commits (and the session closes) as soon as the endpoint returns,
# *before* the response is sent. With the default "request" scope the client could receive "200 OK"
# and immediately read stale data, and a failed commit would be reported to the client as success.
DbSession = Annotated[Session, Depends(get_db, scope="function")]


def get_config(db: DbSession) -> AppConfig:
    return config_service.get(db)


Config = Annotated[AppConfig, Depends(get_config)]


def authenticated_store(request: Request, config: Config) -> StoreRecord:
    """Server-to-server calls from a store authenticate with that store's API key (Bearer or X-API-Key)."""
    key = bearer_token(request) or request.headers.get("x-api-key", "")
    store = config.store_by_api_key(key) if key else None
    if store is None:
        raise Unauthorized("Invalid or missing API key")
    if not store.active:
        raise Unauthorized("This store is disabled")
    return store


ApiStore = Annotated[StoreRecord, Depends(authenticated_store)]


def require_admin(request: Request, config: Config) -> None:
    max_age = get_settings().admin_token_ttl_hours * 3600
    if not AdminTokens.verify(config.secret, bearer_token(request), max_age):
        raise Unauthorized("Not authenticated")


def base_url(request: Request) -> str:
    """Public base URL used to build links (PUBLIC_URL, else whatever host the request came in on)."""
    return get_settings().public_url or str(request.base_url)


def admin_store(config: Config, store: Annotated[int | None, Query()] = None) -> StoreRecord:
    """The store an admin settings call is about (``?store=<id>``; the default store when omitted)."""
    if store is None:
        return config.default_store
    record = config.store_by_id(store)
    if record is None:
        raise NotFound("Store not found")
    return record


def store_filter(config: Config, store: Annotated[int | None, Query()] = None) -> int | None:
    """Which store's data a list/report shows: ``?store=<id>``; omitted means all stores."""
    if store is not None and config.store_by_id(store) is None:
        raise NotFound("Store not found")
    return store


AdminStore = Annotated[StoreRecord, Depends(admin_store)]
StoreScope = Annotated[int | None, Depends(store_filter)]
AdminAuth = Depends(require_admin)
