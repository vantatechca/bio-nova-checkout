from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, and_, case, func, select, true
from sqlalchemy.orm import Session

from app.models import CheckoutSession, Order, OrderStatus, PaymentStatus, SessionStatus
from app.repositories._time import local_day


class AttributionRepository:
    def __init__(self, db: Session, store_id: int | None = None) -> None:
        self.db = db
        self.store_id = store_id  # None = all stores

    @property
    def _scope(self) -> ColumnElement[bool]:
        return CheckoutSession.store_id == self.store_id if self.store_id is not None else true()

    def by_campaign(
        self, since: datetime, limit: int = 50, until: datetime | None = None
    ) -> list[tuple[str, int, int, int, int]]:
        """One row per ``utm_campaign`` (sessions, viewed, orders placed, revenue), busiest campaign first.

        A session with no ``utm_campaign`` but a known ad click id (e.g. a Google Ads click that only carries
        ``gclid``, with no campaign name in the destination URL) is grouped by its click network instead of
        collapsing into "(none)" -- that label is reserved for truly untagged traffic.
        """
        label = case(
            (CheckoutSession.utm_campaign != "", CheckoutSession.utm_campaign),
            (CheckoutSession.click_provider != "", func.concat(CheckoutSession.click_provider, " (no campaign tag)")),
            else_="(none)",
        )
        n = func.count(CheckoutSession.id)
        revenue = func.coalesce(
            func.sum(
                case(
                    (
                        and_(Order.payment_status == PaymentStatus.PAID, Order.status != OrderStatus.REFUNDED),
                        Order.total,
                    ),
                    else_=0,
                )
            ),
            0,
        )

        def count_if(expr: ColumnElement[bool]):
            return func.coalesce(func.sum(case((expr, 1), else_=0)), 0)

        rows = self.db.execute(
            select(
                label,
                n,
                count_if(CheckoutSession.viewed_at.is_not(None)),
                count_if(CheckoutSession.status == SessionStatus.COMPLETE),
                revenue,
            )
            .select_from(CheckoutSession)
            .outerjoin(Order, Order.public_id == CheckoutSession.order_id)
            .where(
                CheckoutSession.created_at.between(since, until)
                if until is not None
                else CheckoutSession.created_at >= since,
                self._scope,
            )
            .group_by(label)
            .order_by(n.desc())
            .limit(limit)
        ).all()
        return [
            (campaign, int(sessions), int(viewed), int(orders), int(revenue))
            for campaign, sessions, viewed, orders, revenue in rows
        ]

    def sessions_vs_arrivals(
        self,
        since: datetime,
        tz_offset_minutes: int,
        until: datetime | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[tuple]:
        """Sessions created vs ever opened ("pressed Checkout" vs "arrived"), excluding internal/test sessions,
        one row per local day x store x campaign x search term x ad-click-id presence. Bucketed by the session's
        own ``created_at`` day, not the day it was (maybe later) viewed -- this answers "of what we created that
        day, how much got opened," not "how many opens happened that day."
        """
        s = CheckoutSession
        local = local_day(s.created_at, tz_offset_minutes)
        has_click = s.click_id != ""
        created = func.count(s.id)
        arrived = func.coalesce(func.sum(case((s.viewed_at.is_not(None), 1), else_=0)), 0)
        rows = self.db.execute(
            select(local, s.store_id, s.utm_campaign, s.utm_term, has_click, created, arrived)
            .where(
                s.created_at.between(since, until) if until is not None else s.created_at >= since,
                self._scope,
                s.is_internal.is_(False),
            )
            .group_by(local, s.store_id, s.utm_campaign, s.utm_term, has_click)
            .order_by(local.desc(), created.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [
            (day.isoformat(), store_id, campaign, term, bool(click), int(cr), int(ar))
            for day, store_id, campaign, term, click, cr, ar in rows
        ]
