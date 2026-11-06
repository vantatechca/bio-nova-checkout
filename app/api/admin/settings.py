from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import Config, DbSession, base_url
from app.models.types import utcnow
from app.repositories import OutboxRepository
from app.schemas.checkout import CreateSessionIn, LineItemIn, SessionOut
from app.schemas.settings import StoreSettingsOut, StoreSettingsUpdate
from app.services import checkout
from app.services import settings as settings_service

router = APIRouter(prefix="/api/admin", tags=["admin: settings"])


@router.get("/settings", response_model=StoreSettingsOut)
def get_settings_view(request: Request, db: DbSession, config: Config):
    deliveries = OutboxRepository(db).recent_webhooks(50)
    return StoreSettingsOut(
        **config.store.model_dump(),
        public_url=base_url(request),
        webhook_log=[
            {
                "id": d.id,
                "at": d.created_at.isoformat(),
                "event": d.event,
                "order": d.order_number,
                "url": d.url,
                "status": d.http_status,
                "error": d.error,
                "attempts": d.attempts,
                "state": d.state,
            }
            for d in deliveries
        ],
    )


@router.put("/settings")
def update_settings(data: StoreSettingsUpdate, db: DbSession, config: Config) -> dict[str, bool]:
    settings_service.update_store(db, config, data)
    return {"ok": True}


@router.post("/settings/rotate-key")
def rotate_key(db: DbSession, config: Config) -> dict[str, str]:
    return {"apiKey": settings_service.rotate_api_key(db, config)}


@router.post("/settings/rotate-webhook-secret")
def rotate_webhook_secret(db: DbSession, config: Config) -> dict[str, str]:
    return {"webhookSecret": settings_service.rotate_webhook_secret(db, config)}


@router.post("/test-session", response_model=SessionOut, status_code=201)
def create_test_session(request: Request, db: DbSession, config: Config):
    """A throwaway sample cart so the checkout page can be tried without a connected store."""
    base = base_url(request).rstrip("/")
    session = checkout.create_session(
        db,
        config,
        CreateSessionIn(
            items=[
                LineItemIn(name="Sample T-shirt", unit_amount=2500, quantity=2, description="Size M"),
                LineItemIn(name="Sample Mug", unit_amount=1200, quantity=1),
            ],
            success_url=f"{base}/static/demo/thank-you.html",
            cancel_url=f"{base}/admin",
            external_ref=f"TEST-{int(utcnow().timestamp())}",
        ),
    )
    return checkout.session_out(session, base)
