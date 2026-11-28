from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import Config, DbSession, StoreScope
from app.schemas.reports import ArrivalsOut, AttemptStatsOut, AttributionOut, RevenueOut, StatsOut, VisitRow, VisitsOut
from app.services import reports

router = APIRouter(prefix="/api/admin", tags=["admin: reports"])

# ``tz`` is the browser's Date.getTimezoneOffset() so "today" and daily buckets match the admin's local days.
TzOffset = Query(default=0, ge=-900, le=900)
DaysQuery = Query(default=30, ge=1, le=reports.MAX_DAYS)
# An exact calendar window (inclusive, "YYYY-MM-DD"); give both to use this instead of ``days``.
DateFromQuery = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
DateToQuery = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
ArrivalsLimitQuery = Query(default=200, ge=1, le=2000)


@router.get("/stats", response_model=StatsOut)
def stats(db: DbSession, config: Config, store: StoreScope):
    return reports.stats(db, config, store)


@router.get("/revenue", response_model=RevenueOut)
def revenue(
    db: DbSession,
    config: Config,
    store: StoreScope,
    days: int = DaysQuery,
    tz: int = TzOffset,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    return reports.revenue_report(db, config, days, tz, store, date_from, date_to)


@router.get("/visits", response_model=VisitsOut)
def visits(
    db: DbSession,
    store: StoreScope,
    days: int = DaysQuery,
    tz: int = TzOffset,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    return reports.visits_report(db, days, tz, store, date_from, date_to)


@router.get("/attribution", response_model=AttributionOut)
def attribution(
    db: DbSession,
    config: Config,
    store: StoreScope,
    days: int = DaysQuery,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    return reports.attribution_report(db, config, days, store, date_from, date_to)


@router.get("/attempts", response_model=AttemptStatsOut)
def attempts(
    db: DbSession,
    store: StoreScope,
    days: int = DaysQuery,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    return reports.attempts_report(db, days, store, date_from, date_to)


@router.get("/visits/lookup", response_model=list[VisitRow])
def visits_lookup(
    db: DbSession,
    store: StoreScope,
    ip: str = Query(default="", max_length=45),
    days: int = DaysQuery,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    """``ip`` filters by prefix; left empty, this is just the most recent visits."""
    return reports.visits_by_ip(db, ip, days, store, limit, offset, date_from, date_to)


@router.get("/arrivals", response_model=ArrivalsOut)
def arrivals(
    db: DbSession,
    store: StoreScope,
    days: int = DaysQuery,
    tz: int = TzOffset,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
    limit: int = ArrivalsLimitQuery,
    offset: int = Query(default=0, ge=0),
):
    """The checkout-arrival KPI feed: unique arrivals (internal traffic excluded) per day/store/campaign/term/
    click-id-presence/device/city, plus sessions-created-vs-arrived for the same campaign/term/click-id split."""
    return reports.arrivals_report(db, days, tz, store, date_from, date_to, limit, offset)
