from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import CheckoutSession, SessionStatus


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

    def purge_abandoned(self, expired_before: datetime) -> int:
        """Deletes sessions that never turned into an order. Completed sessions are kept."""
        result = self.db.execute(
            delete(CheckoutSession).where(
                CheckoutSession.status != SessionStatus.COMPLETE, CheckoutSession.expires_at < expired_before
            )
        )
        return result.rowcount or 0
