"""Customer / admin emails: templates, queueing and delivery."""

from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import EmailLog, EmailStatus, Order, PaymentStatus
from app.models.types import utcnow
from app.repositories import OutboxRepository
from app.schemas.settings import SmtpSettings
from app.services.config import AppConfig
from app.services.money import format_money
from app.services.smtp import SmtpError, send_mail

EMAIL_TYPES = ("confirmation", "paid", "shipped", "cancelled", "admin")
MAX_ATTEMPTS = 3
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=10))  # before attempt 2 and 3


# ---------------------------------------------------------------- templates
def render_email(email_type: str, order: Order, store_name: str) -> tuple[str, str]:
    """Returns ``(subject, plain_text_body)``."""
    total = format_money(order.total, order.currency)
    lines = "\n".join(
        f"  {i.quantity} x {i.name} - {format_money(i.unit_amount * i.quantity, order.currency)}" for i in order.items
    )
    summary = (
        f"Order #{order.number}\n{lines}\n"
        f"  Shipping: {format_money(order.shipping, order.currency)}\n"
        f"  Tax: {format_money(order.tax, order.currency)}\n  Total: {total}"
    )
    greeting = f"Hi {order.customer_name},\n\n"
    signoff = f"\n\nThanks,\n{store_name}"

    if email_type == "confirmation":
        if order.payment_status == PaymentStatus.PAID:
            lead = "Thanks for your order. Your payment has been received and we're getting it ready.\n\n"
        else:
            how = order.payment_instructions or order.payment_method_label
            lead = (
                f"Thanks for your order. To complete it, please pay as follows:\n\n{how}\n\n"
                "We'll start processing as soon as your payment arrives.\n\n"
            )
        return f"Order #{order.number} received - {store_name}", greeting + lead + summary + signoff
    if email_type == "paid":
        ref = f" (ref {order.payment_reference})" if order.payment_reference else ""
        body = f"We've received your payment of {total}{ref}. Your order is now being processed.\n\n"
        return f"Payment received for order #{order.number} - {store_name}", greeting + body + summary + signoff
    if email_type == "shipped":
        tracking = f"\nTracking number: {order.tracking_number}" if order.tracking_number else ""
        body = f"Good news - your order is on its way.{tracking}\n\n"
        return f"Order #{order.number} has shipped - {store_name}", greeting + body + summary + signoff
    if email_type == "cancelled":
        body = (
            f"Your order #{order.number} has been cancelled. "
            "If you didn't expect this or already paid, just reply to this email."
        )
        return f"Order #{order.number} cancelled - {store_name}", greeting + body + signoff
    if email_type == "admin":
        body = (
            f"New order #{order.number}\nPayment: {order.payment_method_label} - {order.payment_status}\n"
            f"Customer: {order.customer_name} <{order.customer_email}>\n\n{summary}\n\nManage it in the admin: /admin"
        )
        return f"New order #{order.number} - {total} ({order.payment_method_label})", body
    raise ValueError(f"Unknown email type: {email_type}")


# ---------------------------------------------------------------- queueing
def queue_email(db: Session, config: AppConfig, email_type: str, order: Order) -> EmailLog | None:
    """Adds an email to the outbox (same transaction as the change that triggered it)."""
    if not getattr(config.email.notify, email_type):
        return None
    recipient = config.email.admin_email if email_type == "admin" else order.customer_email
    if not recipient:
        return None
    subject, body = render_email(email_type, order, config.store.store_name)
    configured = config.email.smtp.configured
    email = EmailLog(
        id=f"em_{secrets.token_hex(6)}",
        type=email_type,
        order_number=order.number,
        to_addr=recipient,
        subject=subject[:500],
        body=body,
        status=EmailStatus.QUEUED if configured else EmailStatus.SKIPPED,
        error=None if configured else "SMTP not configured",
        next_attempt_at=utcnow() if configured else None,
    )
    OutboxRepository(db).add_email(email)
    return email


# ---------------------------------------------------------------- delivery
def attempt_delivery(smtp: SmtpSettings, email: EmailLog, *, auto_retry: bool = True) -> None:
    """Tries once and records the outcome on the row (the caller commits).

    With ``auto_retry`` a failure schedules another attempt until ``MAX_ATTEMPTS`` is reached.
    """
    if not smtp.configured:
        email.status, email.error, email.next_attempt_at = EmailStatus.SKIPPED, "SMTP not configured", None
        return
    email.attempts += 1
    try:
        send_mail(smtp, to=email.to_addr, subject=email.subject, body=email.body)
    except SmtpError as exc:
        email.error = str(exc)[:500]
        if auto_retry and email.attempts < MAX_ATTEMPTS:
            email.status = EmailStatus.QUEUED
            email.next_attempt_at = utcnow() + RETRY_DELAYS[email.attempts - 1]
        else:
            email.status, email.next_attempt_at = EmailStatus.FAILED, None
        return
    email.status, email.error, email.next_attempt_at, email.sent_at = EmailStatus.SENT, None, None, utcnow()
