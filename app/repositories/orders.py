from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models import Order, OrderStatus, PaymentStatus

# The admin's "Failed / Cancelled" tab: cancelled or refunded orders and failed or refunded payments.
FAILED: ColumnElement[bool] = or_(
    Order.status.in_((OrderStatus.CANCELLED, OrderStatus.REFUNDED)),
    Order.payment_status.in_((PaymentStatus.FAILED, PaymentStatus.REFUNDED)),
)
TAB_FILTERS: dict[str, ColumnElement[bool]] = {
    "failed": FAILED,
    "paid": and_(~FAILED, Order.payment_status == PaymentStatus.PAID),
    "pending": and_(~FAILED, Order.payment_status == PaymentStatus.PENDING),
}

# Revenue counts paid, non-refunded orders; the "paid at" moment falls back to creation time.
PAID_AT = func.coalesce(Order.paid_at, Order.created_at)


def _paid_revenue(currency: str) -> ColumnElement[bool]:
    return and_(
        Order.payment_status == PaymentStatus.PAID, Order.status != OrderStatus.REFUNDED, Order.currency == currency
    )


@dataclass
class OrderCounts:
    total: int
    pending: int
    paid: int
    failed: int
    by_status: dict[str, int]
    paid_revenue: int


@dataclass
class RevenueSums:
    all_time: int
    today: int
    last7: int
    last30: int


class OrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- single orders
    def add(self, order: Order) -> None:
        self.db.add(order)
        self.db.flush()  # assigns the AUTO_INCREMENT order number

    @staticmethod
    def _key_filter(key: str) -> ColumnElement[bool]:
        """Orders can be addressed by public id (``ord_...``) or by order number."""
        if key.isdigit() and len(key) <= 15:
            return or_(Order.public_id == key, Order.number == int(key))
        return Order.public_id == key

    def get(self, key: str) -> Order | None:
        return self.db.scalars(select(Order).where(self._key_filter(key))).first()

    def get_for_update(self, key: str) -> Order | None:
        return self.db.scalars(select(Order).where(self._key_filter(key)).with_for_update()).first()

    # ---- listing
    def list(
        self,
        *,
        tab: str | None = None,
        status: str | None = None,
        search: str | None = None,
        external_ref: str | None = None,
        limit: int = 500,
    ) -> tuple[list[Order], bool]:
        stmt = select(Order)
        if tab in TAB_FILTERS:
            stmt = stmt.where(TAB_FILTERS[tab])
        if status:
            stmt = stmt.where(Order.status == status)
        if external_ref:
            stmt = stmt.where(Order.external_ref == external_ref)
        if search:
            like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            stmt = stmt.where(
                or_(
                    cast(Order.number, String).like(like),
                    Order.customer_name.like(like),
                    Order.customer_email.like(like),
                    Order.external_ref.like(like),
                    Order.tracking_number.like(like),
                )
            )
        rows = list(self.db.scalars(stmt.order_by(Order.number.desc()).limit(limit + 1)))
        return rows[:limit], len(rows) > limit

    # ---- aggregates
    def counts(self, currency: str) -> OrderCounts:
        def flag(expr: ColumnElement[bool]):
            return func.coalesce(func.sum(case((expr, 1), else_=0)), 0)

        total, pending, paid, failed = self.db.execute(
            select(
                func.count(Order.number),
                flag(TAB_FILTERS["pending"]),
                flag(TAB_FILTERS["paid"]),
                flag(TAB_FILTERS["failed"]),
            )
        ).one()
        by_status = dict(self.db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
        revenue = self.db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(_paid_revenue(currency)))
        return OrderCounts(
            total=int(total),
            pending=int(pending),
            paid=int(paid),
            failed=int(failed),
            by_status={k: int(v) for k, v in by_status.items()},
            paid_revenue=int(revenue),
        )

    def revenue_sums(
        self, currency: str, *, start_of_today: datetime, last7: datetime, last30: datetime
    ) -> RevenueSums:
        def since(moment: datetime):
            return func.coalesce(func.sum(case((moment <= PAID_AT, Order.total), else_=0)), 0)

        row = self.db.execute(
            select(func.coalesce(func.sum(Order.total), 0), since(start_of_today), since(last7), since(last30)).where(
                _paid_revenue(currency)
            )
        ).one()
        return RevenueSums(*(int(v) for v in row))

    def paid_since(self, currency: str, since: datetime) -> list[tuple[int, datetime]]:
        rows = self.db.execute(select(Order.total, PAID_AT).where(_paid_revenue(currency), since <= PAID_AT)).all()
        return [(int(total), paid_at) for total, paid_at in rows]

    def revenue_by_method(self, currency: str) -> list[tuple[str, int, int]]:
        amount = func.sum(Order.total)
        rows = self.db.execute(
            select(Order.payment_method_label, func.count(), amount)
            .where(_paid_revenue(currency))
            .group_by(Order.payment_method_label)
            .order_by(amount.desc())
        ).all()
        return [(label, int(n), int(total)) for label, n, total in rows]

    def awaiting_payment(self, currency: str) -> tuple[int, int]:
        total, count = self.db.execute(
            select(func.coalesce(func.sum(Order.total), 0), func.count()).where(
                TAB_FILTERS["pending"], Order.currency == currency
            )
        ).one()
        return int(total), int(count)

    def refunded(self, currency: str) -> tuple[int, int]:
        total, count = self.db.execute(
            select(func.coalesce(func.sum(Order.total), 0), func.count()).where(
                or_(Order.payment_status == PaymentStatus.REFUNDED, Order.status == OrderStatus.REFUNDED),
                Order.currency == currency,
            )
        ).one()
        return int(total), int(count)

    def count_other_currency(self, currency: str) -> int:
        return int(self.db.scalar(select(func.count()).where(Order.currency != currency)) or 0)
