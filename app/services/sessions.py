"""Abandoned checkout sessions and a per-session activity timeline, for support and diagnosis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import CheckoutEvent, EmailLog, Order, PaymentAttempt, Visit
from app.repositories import SessionRepository


@dataclass(frozen=True)
class AbandonedSession:
    id: str
    store_id: int
    created_at: datetime
    viewed_at: datetime | None
    customer_name: str
    customer_email: str
    total: int
    currency: str
    steps: list[str]


def abandoned_sessions(
    db: Session, hours: int, store_id: int | None = None, limit: int = 200
) -> list[AbandonedSession]:
    sessions = SessionRepository(db).abandoned(hours, store_id, limit)
    if not sessions:
        return []
    ids = [s.id for s in sessions]
    steps_by_session: dict[str, list[str]] = {}
    rows = db.execute(select(CheckoutEvent.session_id, CheckoutEvent.step).where(CheckoutEvent.session_id.in_(ids)))
    for session_id, step in rows:
        steps_by_session.setdefault(session_id, []).append(step)
    return [
        AbandonedSession(
            id=s.id,
            store_id=s.store_id,
            created_at=s.created_at,
            viewed_at=s.viewed_at,
            customer_name=s.customer_name,
            customer_email=s.customer_email,
            total=s.total,
            currency=s.currency,
            steps=steps_by_session.get(s.id, []),
        )
        for s in sessions
    ]


@dataclass(frozen=True)
class TimelineItem:
    at: datetime
    kind: str  # session | visit | step | payment | order | email
    text: str


def session_timeline(db: Session, session_id: str) -> list[TimelineItem]:
    session = SessionRepository(db).get(session_id)
    if session is None:
        raise NotFound("Session not found")

    items = [TimelineItem(at=session.created_at, kind="session", text="Checkout session created")]
    for v in db.scalars(select(Visit).where(Visit.session_id == session_id)):
        items.append(TimelineItem(at=v.at, kind="visit", text=f"Viewed checkout ({v.device})"))
    for e in db.scalars(select(CheckoutEvent).where(CheckoutEvent.session_id == session_id)):
        items.append(TimelineItem(at=e.at, kind="step", text=f"Reached step: {e.step}"))
    for a in db.scalars(select(PaymentAttempt).where(PaymentAttempt.session_id == session_id)):
        detail = f" ({a.reason})" if a.reason else ""
        items.append(TimelineItem(at=a.at, kind="payment", text=f"Payment {a.outcome}{detail}"))

    order = db.scalars(select(Order).where(Order.session_id == session_id)).first()
    if order is not None:
        items += [TimelineItem(at=h.at, kind="order", text=h.text) for h in order.history]
        for email in db.scalars(select(EmailLog).where(EmailLog.order_number == order.number)):
            items.append(
                TimelineItem(at=email.created_at, kind="email", text=f"Email: {email.subject} ({email.status})")
            )

    items.sort(key=lambda i: i.at)
    return items
