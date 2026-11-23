from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement, and_, case, func, select, true
from sqlalchemy.orm import Session

from app.models import CheckoutSession, Order, OrderStatus, PaymentStatus, SessionStatus


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
