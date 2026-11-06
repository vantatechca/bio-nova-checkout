"""Admin dashboards: order counts, revenue and visit analytics."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import OrderStatus
from app.models.types import utcnow
from app.repositories import OrderRepository, VisitRepository
from app.schemas.reports import (
    DailyRevenue,
    DailyVisits,
    Funnel,
    LabelCount,
    MethodRevenue,
    RevenueOut,
    StatsOut,
    TabCounts,
    VisitsOut,
)
from app.services.config import AppConfig

ALLOWED_RANGES = (7, 30, 90)


# ---------------------------------------------------------------- local-day helpers
# The browser sends ``tz`` = JS ``Date.getTimezoneOffset()`` (minutes *behind* UTC), so local = UTC - tz.
def local_day(moment: datetime, tz: int) -> str:
    return (moment - timedelta(minutes=tz)).date().isoformat()


def local_day_start(day: str, tz: int) -> datetime:
    return datetime.fromisoformat(day + "T00:00:00+00:00") + timedelta(minutes=tz)


def day_range(days: int, tz: int, now: datetime | None = None) -> list[str]:
    now = now or utcnow()
    return [local_day(now - timedelta(days=i), tz) for i in range(days - 1, -1, -1)]


def clamp_days(days: int) -> int:
    return days if days in ALLOWED_RANGES else 30


# ---------------------------------------------------------------- reports
def stats(db: Session, config: AppConfig) -> StatsOut:
    c = OrderRepository(db).counts(config.store.currency)
    return StatsOut(
        total_orders=c.total,
        by_status={s: c.by_status.get(s, 0) for s in OrderStatus.ALL},
        paid_revenue=c.paid_revenue,
        currency=config.store.currency,
        counts=TabCounts(pending=c.pending, paid=c.paid, failed=c.failed),
    )


def revenue_report(db: Session, config: AppConfig, days: int, tz: int) -> RevenueOut:
    repo, currency, now = OrderRepository(db), config.store.currency, utcnow()
    keys = day_range(days, tz, now)
    sums = repo.revenue_sums(
        currency,
        start_of_today=local_day_start(local_day(now, tz), tz),
        last7=now - timedelta(days=7),
        last30=now - timedelta(days=30),
    )
    daily = {k: DailyRevenue(date=k, amount=0, orders=0) for k in keys}
    period_total = period_orders = 0
    for total, paid_at in repo.paid_since(currency, local_day_start(keys[0], tz)):
        bucket = daily.get(local_day(paid_at, tz))
        if bucket:
            bucket.amount += total
            bucket.orders += 1
            period_total += total
            period_orders += 1
    awaiting_total, awaiting_count = repo.awaiting_payment(currency)
    refunded_total, refunded_count = repo.refunded(currency)
    return RevenueOut(
        currency=currency,
        days=days,
        excluded_other_currency=repo.count_other_currency(currency),
        today=sums.today,
        last7=sums.last7,
        last30=sums.last30,
        all_time=sums.all_time,
        period_total=period_total,
        period_orders=period_orders,
        avg_order=round(period_total / period_orders) if period_orders else 0,
        awaiting_payment=awaiting_total,
        awaiting_count=awaiting_count,
        refunded=refunded_total,
        refunded_count=refunded_count,
        daily=[daily[k] for k in keys],
        by_method=[
            MethodRevenue(label=label, orders=n, amount=amount) for label, n, amount in repo.revenue_by_method(currency)
        ],
    )


def visits_report(db: Session, days: int, tz: int) -> VisitsOut:
    repo = VisitRepository(db)
    since = utcnow() - timedelta(days=days)
    views, visitors = repo.totals(since)
    per_day = repo.daily(since, tz)
    funnel = repo.funnel(since)
    return VisitsOut(
        days=days,
        views=views,
        visitors=visitors,
        funnel=Funnel(
            created=funnel.created,
            viewed=funnel.viewed,
            ordered=funnel.ordered,
            conversion=round(funnel.converted / funnel.viewed * 100, 1) if funnel.viewed else 0.0,
        ),
        daily=[
            DailyVisits(date=k, views=per_day.get(k, (0, 0))[0], visitors=per_day.get(k, (0, 0))[1])
            for k in day_range(days, tz)
        ],
        devices=[LabelCount(label=label, count=n) for label, n in repo.devices(since)],
        referrers=[LabelCount(label=label, count=n) for label, n in repo.referrers(since)],
    )
