from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminStore, DbSession
from app.schemas.settings import new_secret
from app.services import client_payment_api, stores

router = APIRouter(prefix="/api/admin/card", tags=["admin: card payments"])


@router.post("/test")
def test_client_api(store: AdminStore) -> dict[str, bool]:
    """Sends the client's API a signed ``{"type": "ping"}``; it must answer ``{"ok": true}``."""
    client_payment_api.ping(store.settings)
    return {"ok": True}


@router.post("/rotate-secret")
def rotate_signing_secret(db: DbSession, store: AdminStore) -> dict[str, str]:
    """New secret for signing our requests. The client must be given the new value."""
    settings = store.settings.model_copy(update={"client_api_secret": new_secret("capi")})
    stores.save_settings(db, store.id, settings)
    return {"clientApiSecret": settings.client_api_secret}
