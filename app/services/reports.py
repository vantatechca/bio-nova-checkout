"""Admin dashboards: order counts, revenue and visit analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.errors import BadRequest
from app.models import OrderStatus
from app.models.types import utcnow
from app.repositories import AttributionRepository, OrderRepository, PaymentAttemptRepository, VisitRepository
from app.schemas.reports import (
    AttemptRow,
    AttemptStatsOut,
    AttributionOut,
    CampaignRow,
    DailyRevenue,
    DailyVisits,
    Funnel,
    LabelCount,
    MethodRevenue,
    RecentAttempt,
    RevenueOut,
    StatsOut,
    TabCounts,
    VisitRow,
    VisitsOut,
)
from app.services.config import AppConfig

MAX_DAYS = 366  # a caller asking for an exact date_from/date_to range is capped at the same span


# ---------------------------------------------------------------- local-day helpers
# The browser (or a bot) sends ``tz`` = JS ``Date.getTimezoneOffset()`` (minutes *behind* UTC), so local = UTC - tz.
def local_day(moment: datetime, tz: int) -> str:
    return (moment - timedelta(minutes=tz)).date().isoformat()


def local_day_start(day: str, tz: int) -> datetime:
    return datetime.fromisoformat(day + "T00:00:00+00:00") + timedelta(minutes=tz)


def day_range(days: int, tz: int, now: datetime | None = None) -> list[str]:
    now = now or utcnow()
    return [local_day(now - timedelta(days=i), tz) for i in range(days - 1, -1, -1)]


def _parse_date(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise BadRequest(f"{field} must be an ISO date (YYYY-MM-DD)") from exc


@dataclass(frozen=True)
class Window:
    since: datetime
    until: datetime | None  # None = open-ended, up to now
    days: int
    day_keys: list[str]


def resolve_window(days: int, tz: int, date_from: str | None = None, date_to: str | None = None) -> Window:
    """The window a report covers: an exact ``date_from``..``date_to`` calendar range (inclusive, in the
    caller's local days) when both are given, otherwise the last ``days`` days up to now. Either way, every
    report gets back the matching list of local-day keys to bucket a daily breakdown by."""
    if date_from or date_to:
        if not (date_from and date_to):
            raise BadRequest("date_from and date_to must both be given")
        start, end = _parse_date(date_from, "date_from").date(), _parse_date(date_to, "date_to").date()
        if end < start:
            raise BadRequest("date_to must not be before date_from")
        span = (end - start).days + 1
        if span > MAX_DAYS:
            raise BadRequest(f"date_from/date_to cannot span more than {MAX_DAYS} days")
        keys = [(start + timedelta(days=i)).isoformat() for i in range(span)]
        since = local_day_start(keys[0], tz)
        until = local_day_start(keys[-1], tz) + timedelta(days=1) - timedelta(microseconds=1)
        return Window(since=since, until=until, days=span, day_keys=keys)
    now = utcnow()
    return Window(since=now - timedelta(days=days), until=None, days=days, day_keys=day_range(days, tz, now))


# ---------------------------------------------------------------- reports
def _currency(config: AppConfig, store_id: int | None) -> str:
    """A store's own currency; for the all-stores view, the default store's."""
    store = config.store_by_id(store_id) if store_id is not None else None
    return (store or config.default_store).settings.currency


def stats(db: Session, config: AppConfig, store_id: int | None = None) -> StatsOut:
    currency = _currency(config, store_id)
    c = OrderRepository(db, store_id).counts(currency)
    return StatsOut(
        total_orders=c.total,
        by_status={s: c.by_status.get(s, 0) for s in OrderStatus.ALL},
        paid_revenue=c.paid_revenue,
        currency=currency,
        counts=TabCounts(pending=c.pending, paid=c.paid, failed=c.failed),
    )


def revenue_report(
    db: Session,
    config: AppConfig,
    days: int,
    tz: int,
    store_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> RevenueOut:
    currency = _currency(config, store_id)
    repo, now = OrderRepository(db, store_id), utcnow()
    window = resolve_window(days, tz, date_from, date_to)
    sums = repo.revenue_sums(
        currency,
        start_of_today=local_day_start(local_day(now, tz), tz),
        last7=now - timedelta(days=7),
        last30=now - timedelta(days=30),
    )
    daily = {k: DailyRevenue(date=k, amount=0, orders=0) for k in window.day_keys}
    period_total = period_orders = 0
    for total, paid_at in repo.paid_since(currency, window.since, window.until):
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
        days=window.days,
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
        daily=[daily[k] for k in window.day_keys],
        by_method=[
            MethodRevenue(label=label, orders=n, amount=amount) for label, n, amount in repo.revenue_by_method(currency)
        ],
    )


def visits_report(
    db: Session,
    days: int,
    tz: int,
    store_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> VisitsOut:
    repo = VisitRepository(db, store_id)
    window = resolve_window(days, tz, date_from, date_to)
    views, visitors = repo.totals(window.since, window.until)
    per_day = repo.daily(window.since, tz, window.until)
    funnel = repo.funnel(window.since, window.until)
    return VisitsOut(
        days=window.days,
        views=views,
        visitors=visitors,
        funnel=Funnel(
            created=funnel.created,
            viewed=funnel.viewed,
            ordered=funnel.ordered,
            conversion=round(funnel.converted / funnel.viewed * 100, 1) if funnel.viewed else 0.0,
            steps=[LabelCount(label=step, count=n) for step, n in repo.steps(window.since, window.until)],
        ),
        daily=[
            DailyVisits(date=k, views=per_day.get(k, (0, 0))[0], visitors=per_day.get(k, (0, 0))[1])
            for k in window.day_keys
        ],
        devices=[LabelCount(label=label, count=n) for label, n in repo.devices(window.since, until=window.until)],
        referrers=[LabelCount(label=label, count=n) for label, n in repo.referrers(window.since, until=window.until)],
    )


def attribution_report(
    db: Session,
    config: AppConfig,
    days: int,
    store_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> AttributionOut:
    window = resolve_window(days, 0, date_from, date_to)
    rows = AttributionRepository(db, store_id).by_campaign(window.since, until=window.until)
    return AttributionOut(
        days=window.days,
        currency=_currency(config, store_id),
        rows=[
            CampaignRow(
                campaign=campaign,
                sessions=sessions,
                viewed=viewed,
                orders=orders,
                revenue=revenue,
                conversion=round(orders / viewed * 100, 1) if viewed else 0.0,
            )
            for campaign, sessions, viewed, orders, revenue in rows
        ],
    )


def attempts_report(
    db: Session,
    days: int,
    store_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    recent_limit: int = 50,
) -> AttemptStatsOut:
    window = resolve_window(days, 0, date_from, date_to)
    repo = PaymentAttemptRepository(db, store_id)
    total, declined, error = repo.counts_since(window.since, window.until)
    recent = repo.recent(window.since, recent_limit + 1, until=window.until)
    return AttemptStatsOut(
        days=window.days,
        total=total,
        declined=declined,
        error=error,
        recovered=repo.recovered_since(window.since, window.until),
        by_reason=[
            AttemptRow(reason=reason, count=n) for reason, n in repo.reason_breakdown(window.since, until=window.until)
        ],
        recent=[
            RecentAttempt(
                at=a.at,
                store_id=a.store_id,
                session_id=a.session_id,
                outcome=a.outcome,
                reason=a.reason,
                attempt_no=a.attempt_no,
            )
            for a in recent[:recent_limit]
        ],
        recent_has_more=len(recent) > recent_limit,
    )


def visits_by_ip(
    db: Session,
    ip_prefix: str,
    days: int,
    store_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[VisitRow]:
    window = resolve_window(days, 0, date_from, date_to)
    rows = VisitRepository(db, store_id).by_ip_prefix(ip_prefix, window.since, limit, offset, window.until)
    return [VisitRow.model_validate(v) for v in rows]
