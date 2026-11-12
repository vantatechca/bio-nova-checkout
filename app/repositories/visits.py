from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, case, delete, func, literal_column, select, true
from sqlalchemy.orm import Session

from app.models import CheckoutSession, SessionStatus, Visit


@dataclass
class FunnelCounts:
    created: int
    viewed: int
    ordered: int
    converted: int  # sessions that were both viewed and ordered


class VisitRepository:
    def __init__(self, db: Session, store_id: int | None = None) -> None:
        self.db = db
        self.store_id = store_id  # None = all stores

    @property
    def _visits(self) -> ColumnElement[bool]:
        return Visit.store_id == self.store_id if self.store_id is not None else true()

    @property
    def _sessions(self) -> ColumnElement[bool]:
        return CheckoutSession.store_id == self.store_id if self.store_id is not None else true()

    def add(self, visit: Visit) -> None:
        self.db.add(visit)
        self.db.flush()

    def seen_since(self, session_id: str, visitor: str, since: datetime) -> bool:
        stmt = (
            select(Visit.id).where(Visit.session_id == session_id, Visit.visitor == visitor, Visit.at > since).limit(1)
        )
        return self.db.scalar(stmt) is not None

    def totals(self, since: datetime) -> tuple[int, int]:
        views, visitors = self.db.execute(
            select(func.count(Visit.id), func.count(func.distinct(Visit.visitor))).where(
                Visit.at >= since, self._visits
            )
        ).one()
        return int(views), int(visitors)

    def daily(self, since: datetime, tz_offset_minutes: int) -> dict[str, tuple[int, int]]:
        """Views and unique visitors per local day. ``tz_offset_minutes`` follows JS ``getTimezoneOffset()``."""
        local = func.date(func.date_sub(Visit.at, literal_column(f"INTERVAL {int(tz_offset_minutes)} MINUTE")))
        rows = self.db.execute(
            select(local, func.count(Visit.id), func.count(func.distinct(Visit.visitor)))
            .where(Visit.at >= since, self._visits)
            .group_by(local)
        ).all()
        return {day.isoformat(): (int(v), int(u)) for day, v, u in rows}

    def devices(self, since: datetime, limit: int = 8) -> list[tuple[str, int]]:
        n = func.count(Visit.id)
        rows = self.db.execute(
            select(Visit.device, n)
            .where(Visit.at >= since, self._visits)
            .group_by(Visit.device)
            .order_by(n.desc())
            .limit(limit)
        ).all()
        return [(label, int(c)) for label, c in rows]

    def referrers(self, since: datetime, limit: int = 8) -> list[tuple[str, int]]:
        label = case((Visit.referrer == "", "(direct / unknown)"), else_=Visit.referrer)
        n = func.count(Visit.id)
        rows = self.db.execute(
            select(label, n).where(Visit.at >= since, self._visits).group_by(label).order_by(n.desc()).limit(limit)
        ).all()
        return [(name, int(c)) for name, c in rows]

    def funnel(self, since: datetime) -> FunnelCounts:
        s = CheckoutSession
        viewed = s.viewed_at.is_not(None)
        ordered = s.status == SessionStatus.COMPLETE

        def count_if(expr):
            return func.coalesce(func.sum(case((expr, 1), else_=0)), 0)

        created, n_viewed, n_ordered, converted = self.db.execute(
            select(func.count(s.id), count_if(viewed), count_if(ordered), count_if(viewed & ordered)).where(
                s.created_at >= since, self._sessions
            )
        ).one()
        return FunnelCounts(int(created), int(n_viewed), int(n_ordered), int(converted))

    def purge(self, older_than: datetime) -> int:
        return self.db.execute(delete(Visit).where(Visit.at < older_than)).rowcount or 0
