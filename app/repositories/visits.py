from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, case, delete, func, select, true
from sqlalchemy.orm import Session

from app.models import STEPS, CheckoutEvent, CheckoutSession, SessionStatus, Visit
from app.repositories._time import local_day


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

    @staticmethod
    def _window(column, since: datetime, until: datetime | None) -> ColumnElement[bool]:
        return column.between(since, until) if until is not None else column >= since

    def totals(self, since: datetime, until: datetime | None = None) -> tuple[int, int]:
        views, visitors = self.db.execute(
            select(func.count(Visit.id), func.count(func.distinct(Visit.visitor))).where(
                self._window(Visit.at, since, until), self._visits
            )
        ).one()
        return int(views), int(visitors)

    def totals_excluding_internal(self, since: datetime, until: datetime | None = None) -> tuple[int, int]:
        """Same as ``totals``, minus visits flagged ``is_internal`` -- a breakdown alongside the "all" totals,
        never a replacement for them."""
        views, visitors = self.db.execute(
            select(func.count(Visit.id), func.count(func.distinct(Visit.visitor))).where(
                self._window(Visit.at, since, until), self._visits, Visit.is_internal.is_(False)
            )
        ).one()
        return int(views), int(visitors)

    def daily(
        self, since: datetime, tz_offset_minutes: int, until: datetime | None = None
    ) -> dict[str, tuple[int, int]]:
        """Views and unique visitors per local day. ``tz_offset_minutes`` follows JS ``getTimezoneOffset()``."""
        local = local_day(Visit.at, tz_offset_minutes)
        rows = self.db.execute(
            select(local, func.count(Visit.id), func.count(func.distinct(Visit.visitor)))
            .where(self._window(Visit.at, since, until), self._visits)
            .group_by(local)
        ).all()
        return {day.isoformat(): (int(v), int(u)) for day, v, u in rows}

    def devices(self, since: datetime, limit: int = 8, until: datetime | None = None) -> list[tuple[str, int]]:
        n = func.count(Visit.id)
        rows = self.db.execute(
            select(Visit.device, n)
            .where(self._window(Visit.at, since, until), self._visits)
            .group_by(Visit.device)
            .order_by(n.desc())
            .limit(limit)
        ).all()
        return [(label, int(c)) for label, c in rows]

    def referrers(self, since: datetime, limit: int = 8, until: datetime | None = None) -> list[tuple[str, int]]:
        label = case((Visit.referrer == "", "(direct / unknown)"), else_=Visit.referrer)
        n = func.count(Visit.id)
        rows = self.db.execute(
            select(label, n)
            .where(self._window(Visit.at, since, until), self._visits)
            .group_by(label)
            .order_by(n.desc())
            .limit(limit)
        ).all()
        return [(name, int(c)) for name, c in rows]

    def by_ip_prefix(
        self, prefix: str, since: datetime, limit: int = 50, offset: int = 0, until: datetime | None = None
    ) -> list[Visit]:
        """Individual visits whose stored IP starts with ``prefix`` (uses ``ix_visits_ip``)."""
        like = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = (
            select(Visit)
            .where(Visit.ip.like(like), self._window(Visit.at, since, until), self._visits)
            .order_by(Visit.at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def arrivals(
        self,
        since: datetime,
        tz_offset_minutes: int,
        until: datetime | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[tuple]:
        """Checkout-page arrivals (unique visitors, internal traffic excluded), one row per local day x store x
        campaign x search term x ad-click-id presence x device x city -- the breakdown a Google Ads-style KPI
        report needs. Joins to ``CheckoutSession`` for the attribution fields, which live there, not on ``Visit``.
        """
        v, s = Visit, CheckoutSession
        local = local_day(v.at, tz_offset_minutes)
        has_click = s.click_id != ""
        arrivals = func.count(func.distinct(v.visitor))
        views = func.count(v.id)
        rows = self.db.execute(
            select(local, v.store_id, s.utm_campaign, s.utm_term, has_click, v.device, v.city, arrivals, views)
            .select_from(v)
            .join(s, s.id == v.session_id)
            .where(self._window(v.at, since, until), self._visits, v.is_internal.is_(False))
            .group_by(local, v.store_id, s.utm_campaign, s.utm_term, has_click, v.device, v.city)
            .order_by(local.desc(), arrivals.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [
            (day.isoformat(), store_id, campaign, term, bool(click), device, city, int(a), int(vw))
            for day, store_id, campaign, term, click, device, city, a, vw in rows
        ]

    def steps(self, since: datetime, until: datetime | None = None) -> list[tuple[str, int]]:
        """Distinct sessions reaching each checkout-form milestone, in the order a customer normally reaches them."""
        scope = CheckoutEvent.store_id == self.store_id if self.store_id is not None else true()
        n = func.count(CheckoutEvent.id)  # (session_id, step) is unique, so this already counts distinct sessions
        counts = dict(
            self.db.execute(
                select(CheckoutEvent.step, n)
                .where(self._window(CheckoutEvent.at, since, until), scope)
                .group_by(CheckoutEvent.step)
            ).all()
        )
        return [(step, int(counts.get(step, 0))) for step in STEPS]

    def funnel(self, since: datetime, until: datetime | None = None) -> FunnelCounts:
        s = CheckoutSession
        viewed = s.viewed_at.is_not(None)
        ordered = s.status == SessionStatus.COMPLETE
        # A session flagged internal (tester/monitoring, see is_internal_request) that was never viewed is just
        # noise in "created" -- excluded from that one count only; the row itself is never deleted or hidden.
        counted = ~(s.is_internal & ~viewed)

        def count_if(expr):
            return func.coalesce(func.sum(case((expr, 1), else_=0)), 0)

        created, n_viewed, n_ordered, converted = self.db.execute(
            select(count_if(counted), count_if(viewed), count_if(ordered), count_if(viewed & ordered)).where(
                self._window(s.created_at, since, until), self._sessions
            )
        ).one()
        return FunnelCounts(int(created), int(n_viewed), int(n_ordered), int(converted))

    def purge(self, older_than: datetime) -> int:
        return self.db.execute(delete(Visit).where(Visit.at < older_than)).rowcount or 0
