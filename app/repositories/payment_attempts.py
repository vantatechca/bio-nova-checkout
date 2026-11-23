from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, case, func, select, true
from sqlalchemy.orm import Session

from app.models import PaymentAttempt


class PaymentAttemptRepository:
    def __init__(self, db: Session, store_id: int | None = None) -> None:
        self.db = db
        self.store_id = store_id  # None = all stores

    @property
    def _scope(self) -> ColumnElement[bool]:
        return PaymentAttempt.store_id == self.store_id if self.store_id is not None else true()

    def add(self, attempt: PaymentAttempt) -> None:
        self.db.add(attempt)
        self.db.flush()

    def count_for(self, session_id: str) -> int:
        return int(
            self.db.scalar(select(func.count(PaymentAttempt.id)).where(PaymentAttempt.session_id == session_id)) or 0
        )

    @staticmethod
    def _window(since: datetime, until: datetime | None) -> ColumnElement[bool]:
        return PaymentAttempt.at.between(since, until) if until is not None else PaymentAttempt.at >= since

    def reason_breakdown(self, since: datetime, limit: int = 8, until: datetime | None = None) -> list[tuple[str, int]]:
        label = func.coalesce(func.nullif(PaymentAttempt.reason, ""), "(no reason given)")
        n = func.count(PaymentAttempt.id)
        rows = self.db.execute(
            select(label, n)
            .where(self._window(since, until), PaymentAttempt.outcome == "declined", self._scope)
            .group_by(label)
            .order_by(n.desc())
            .limit(limit)
        ).all()
        return [(reason, int(c)) for reason, c in rows]

    def recent(
        self, since: datetime, limit: int = 50, offset: int = 0, until: datetime | None = None
    ) -> list[PaymentAttempt]:
        return list(
            self.db.scalars(
                select(PaymentAttempt)
                .where(self._window(since, until), self._scope)
                .order_by(PaymentAttempt.at.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def recovered_since(self, since: datetime, until: datetime | None = None) -> int:
        """Sessions whose latest attempt in the window succeeded after at least one earlier decline."""
        latest = (
            select(PaymentAttempt.session_id, func.max(PaymentAttempt.attempt_no).label("max_attempt"))
            .where(self._window(since, until), self._scope)
            .group_by(PaymentAttempt.session_id)
            .subquery()
        )
        count = self.db.scalar(
            select(func.count())
            .select_from(PaymentAttempt)
            .join(
                latest,
                (PaymentAttempt.session_id == latest.c.session_id)
                & (PaymentAttempt.attempt_no == latest.c.max_attempt),
            )
            .where(PaymentAttempt.outcome == "succeeded", PaymentAttempt.attempt_no > 1)
        )
        return int(count or 0)

    def counts_since(self, since: datetime, until: datetime | None = None) -> tuple[int, int, int]:
        """(total, declined, error) attempts in the window."""
        n = func.count(PaymentAttempt.id)

        def count_if(outcome: str):
            return func.coalesce(func.sum(case((PaymentAttempt.outcome == outcome, 1), else_=0)), 0)

        total, declined, error = self.db.execute(
            select(n, count_if("declined"), count_if("error")).where(self._window(since, until), self._scope)
        ).one()
        return int(total), int(declined), int(error)
