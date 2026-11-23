"""Read-only reporting API for an external bot or analytics tool.

Authenticated with the separate analytics key (``StoreSettings.analytics_key``), never the admin password and
never the full server-to-server API key -- so a third party can read what's happening (attribution, payment
attempts, visits, revenue, abandoned sessions, orders) without being able to change anything: no route here
writes, and none of them return customer PII (name, email, shipping address) or a customer's raw IP address.

Multi-store setups: add ``X-Checkout-Store: <store id>`` to scope a request to one store; left out, a request
covers every store. This is the same header the main server-to-server API (``/api/v1/...``) uses.

Date range: pass ``days`` (default 30, 1-366) for a rolling window up to now, or ``date_from``/``date_to``
(both, "YYYY-MM-DD") for an exact inclusive calendar range -- e.g. ``date_from=2026-11-17&date_to=2026-11-19``.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import AnalyticsCaller, Config, DbSession
from app.schemas.analytics import AnalyticsOrderOut
from app.schemas.reports import AttemptStatsOut, AttributionOut, RevenueOut, StatsOut, VisitRow, VisitsOut
from app.schemas.sessions import AnalyticsAbandonedSessionsOut, TimelineItemOut
from app.services import orders, reports, sessions

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics (read-only)"])

# ``tz`` is the caller's Date.getTimezoneOffset() so "today" and daily buckets match its local days.
TzOffset = Query(default=0, ge=-900, le=900)
DaysQuery = Query(default=30, ge=1, le=reports.MAX_DAYS)
# An exact calendar window (inclusive, "YYYY-MM-DD"); give both to use this instead of ``days``.
DateFromQuery = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
DateToQuery = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
HoursQuery = Query(default=6, ge=1, le=24 * 30)
LimitQuery = Query(default=50, ge=1, le=500)
OffsetQuery = Query(default=0, ge=0)


@router.get("/stats", response_model=StatsOut)
def stats(db: DbSession, config: Config, caller: AnalyticsCaller):
    return reports.stats(db, config, caller.scope)


@router.get("/revenue", response_model=RevenueOut)
def revenue(
    db: DbSession,
    config: Config,
    caller: AnalyticsCaller,
    days: int = DaysQuery,
    tz: int = TzOffset,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    return reports.revenue_report(db, config, days, tz, caller.scope, date_from, date_to)


@router.get("/visits", response_model=VisitsOut)
def visits(
    db: DbSession,
    caller: AnalyticsCaller,
    days: int = DaysQuery,
    tz: int = TzOffset,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    return reports.visits_report(db, days, tz, caller.scope, date_from, date_to)


@router.get("/attribution", response_model=AttributionOut)
def attribution(
    db: DbSession,
    config: Config,
    caller: AnalyticsCaller,
    days: int = DaysQuery,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    return reports.attribution_report(db, config, days, caller.scope, date_from, date_to)


@router.get("/attempts", response_model=AttemptStatsOut)
def attempts(
    db: DbSession,
    caller: AnalyticsCaller,
    days: int = DaysQuery,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
    limit: int = LimitQuery,
):
    return reports.attempts_report(db, days, caller.scope, date_from, date_to, limit)


@router.get("/visits/lookup", response_model=list[VisitRow])
def visits_lookup(
    db: DbSession,
    caller: AnalyticsCaller,
    ip: str = Query(default="", max_length=45),
    days: int = DaysQuery,
    limit: int = LimitQuery,
    offset: int = OffsetQuery,
    date_from: str | None = DateFromQuery,
    date_to: str | None = DateToQuery,
):
    """``ip`` filters by prefix; left empty, this is just the most recent visits. Page with ``offset`` once a
    response comes back with exactly ``limit`` rows (that's the sign there may be more)."""
    return reports.visits_by_ip(db, ip, days, caller.scope, limit, offset, date_from, date_to)


@router.get("/abandoned", response_model=AnalyticsAbandonedSessionsOut)
def abandoned(
    db: DbSession, caller: AnalyticsCaller, hours: int = HoursQuery, limit: int = LimitQuery, offset: int = OffsetQuery
):
    rows, has_more = sessions.abandoned_sessions(db, hours, caller.scope, limit, offset)
    return AnalyticsAbandonedSessionsOut(hours=hours, rows=rows, has_more=has_more)


@router.get("/sessions/{session_id}/timeline", response_model=list[TimelineItemOut])
def timeline(session_id: str, db: DbSession, caller: AnalyticsCaller):
    return sessions.session_timeline(db, session_id, caller.scope)


@router.get("/orders/{key}", response_model=AnalyticsOrderOut)
def order(key: str, db: DbSession, caller: AnalyticsCaller):
    """Look up one order by its number or public id -- in particular, to get its ``session_id`` for
    ``/sessions/{id}/timeline``. No customer name, email, address or raw IP is included; see ``AnalyticsOrderOut``."""
    return orders.get_order(db, key, caller.scope)
