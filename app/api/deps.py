"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import Unauthorized
from app.security import AdminTokens, bearer_token, constant_time_equals
from app.services.config import AppConfig, config_service

# scope="function": the transaction commits (and the session closes) as soon as the endpoint returns,
# *before* the response is sent. With the default "request" scope the client could receive "200 OK"
# and immediately read stale data, and a failed commit would be reported to the client as success.
DbSession = Annotated[Session, Depends(get_db, scope="function")]


def get_config(db: DbSession) -> AppConfig:
    return config_service.get(db)


Config = Annotated[AppConfig, Depends(get_config)]


def require_store(request: Request, config: Config) -> None:
    """Server-to-server calls from the store authenticate with the API key (Bearer or X-API-Key)."""
    key = bearer_token(request) or request.headers.get("x-api-key", "")
    if not key or not constant_time_equals(key, config.store.api_key):
        raise Unauthorized("Invalid or missing API key")


def require_admin(request: Request, config: Config) -> None:
    max_age = get_settings().admin_token_ttl_hours * 3600
    if not AdminTokens.verify(config.secret, bearer_token(request), max_age):
        raise Unauthorized("Not authenticated")


def base_url(request: Request) -> str:
    """Public base URL used to build links (PUBLIC_URL, else whatever host the request came in on)."""
    return get_settings().public_url or str(request.base_url)


StoreAuth = Depends(require_store)
AdminAuth = Depends(require_admin)
