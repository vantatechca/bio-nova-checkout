"""SMTP transport (stdlib ``smtplib``)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.schemas.settings import SmtpSettings

TIMEOUT_SECONDS = 20


class SmtpError(Exception):
    """Delivery failed; the message is safe to show in the admin."""


def send_mail(smtp: SmtpSettings, *, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = smtp.from_address
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid()
    message.set_content(body)

    context = ssl.create_default_context()
    try:
        if smtp.secure:
            client: smtplib.SMTP = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=TIMEOUT_SECONDS, context=context)
        else:
            client = smtplib.SMTP(smtp.host, smtp.port, timeout=TIMEOUT_SECONDS)
        with client:
            client.ehlo()
            if not smtp.secure and client.has_extn("starttls"):
                client.starttls(context=context)
                client.ehlo()
            if smtp.user:
                client.login(smtp.user, smtp.password)
            client.send_message(message)
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        raise SmtpError(str(exc)[:300]) from exc
