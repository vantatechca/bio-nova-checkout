from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, delete, select, true, update
from sqlalchemy.orm import Session

from app.models import CheckoutSession, SessionStatus
from app.models.types import utcnow


class SessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, checkout_session: CheckoutSession) -> None:
        self.db.add(checkout_session)
        self.db.flush()

    def get(self, session_id: str) -> CheckoutSession | None:
        return self.db.get(CheckoutSession, session_id)

    def get_for_update(self, session_id: str) -> CheckoutSession | None:
        """Row-locks the session so concurrent "place order" requests are serialised."""
        stmt = select(CheckoutSession).where(CheckoutSession.id == session_id).with_for_update()
        return self.db.scalars(stmt).first()

    def mark_viewed(self, session_id: str, when: datetime) -> None:
        self.db.execute(
            update(CheckoutSession)
            .where(CheckoutSession.id == session_id, CheckoutSession.viewed_at.is_(None))
            .values(viewed_at=when)
        )

    def abandoned(self, since_hours: int, store_id: int | None = None, limit: int = 200) -> list[CheckoutSession]:
        """Open sessions older than ``since_hours``, newest first: carts that were never finished."""
        scope: ColumnElement[bool] = CheckoutSession.store_id == store_id if store_id is not None else true()
        cutoff = utcnow() - timedelta(hours=since_hours)
        stmt = (
            select(CheckoutSession)
            .where(CheckoutSession.status == SessionStatus.OPEN, CheckoutSession.created_at < cutoff, scope)
            .order_by(CheckoutSession.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def purge_abandoned(self, expired_before: datetime) -> int:
        """Deletes sessions that never turned into an order. Completed sessions are kept."""
        result = self.db.execute(
            delete(CheckoutSession).where(
                CheckoutSession.status != SessionStatus.COMPLETE, CheckoutSession.expires_at < expired_before
            )
        )
        return result.rowcount or 0
