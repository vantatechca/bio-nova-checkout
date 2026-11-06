from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Config, DbSession
from app.schemas.settings import new_secret
from app.services import client_payment_api
from app.services.config import config_service

router = APIRouter(prefix="/api/admin/card", tags=["admin: card payments"])


@router.post("/test")
def test_client_api(config: Config) -> dict[str, bool]:
    """Sends the client's API a signed ``{"type": "ping"}``; it must answer ``{"ok": true}``."""
    client_payment_api.ping(config.store)
    return {"ok": True}


@router.post("/rotate-secret")
def rotate_signing_secret(db: DbSession, config: Config) -> dict[str, str]:
    """New secret for signing our requests. The client must be given the new value."""
    store = config.store.model_copy(update={"client_api_secret": new_secret("capi")})
    config_service.save_store(db, store)
    return {"clientApiSecret": store.client_api_secret}
