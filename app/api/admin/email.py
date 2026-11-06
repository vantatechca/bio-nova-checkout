from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter

from app.api.deps import Config, DbSession
from app.errors import BadRequest, NotFound
from app.models.types import utcnow
from app.repositories import OutboxRepository
from app.schemas.email import EmailLogOut, EmailOverviewOut, EmailStats, RetryOut
from app.schemas.settings import EmailSettingsUpdate, EmailTestIn
from app.services import settings as settings_service
from app.services.emails import attempt_delivery
from app.services.smtp import SmtpError, send_mail

router = APIRouter(prefix="/api/admin/email", tags=["admin: email"])


@router.get("", response_model=EmailOverviewOut)
def overview(db: DbSession, config: Config):
    outbox = OutboxRepository(db)
    stats = outbox.email_stats(utcnow() - timedelta(days=30))
    return EmailOverviewOut(
        settings=settings_service.masked_email_settings(config.email),
        stats=EmailStats(sent=stats.get("sent", 0), failed=stats.get("failed", 0), skipped=stats.get("skipped", 0)),
        log=[
            EmailLogOut(
                id=e.id,
                at=e.created_at,
                type=e.type,
                order=e.order_number,
                to=e.to_addr,
                subject=e.subject,
                status=e.status,
                error=e.error,
                sent_at=e.sent_at,
            )
            for e in outbox.recent_emails(100)
        ],
    )


@router.put("")
def update(data: EmailSettingsUpdate, db: DbSession, config: Config) -> dict[str, bool]:
    settings_service.update_email(db, config, data)
    return {"ok": True}


@router.post("/test")
def send_test(data: EmailTestIn, config: Config) -> dict[str, bool]:
    smtp = config.email.smtp
    if not smtp.configured:
        raise BadRequest("Fill in the SMTP host and From address first")
    try:
        send_mail(
            smtp,
            to=data.to,
            subject=f"Test email from {config.store.store_name}",
            body="If you can read this, your SMTP settings work.",
        )
    except SmtpError as exc:
        raise BadRequest(f"Send failed: {exc}") from exc
    return {"ok": True}


@router.post("/{email_id}/retry", response_model=RetryOut)
def retry(email_id: str, db: DbSession, config: Config):
    email = OutboxRepository(db).get_email(email_id)
    if email is None:
        raise NotFound("Email not found")
    email.attempts = 0
    attempt_delivery(config.email.smtp, email, auto_retry=False)
    return RetryOut(status=email.status, error=email.error)
