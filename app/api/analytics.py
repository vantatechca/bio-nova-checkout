"""Read-only reporting API for an external bot or analytics tool.

Authenticated with the separate analytics key (``StoreSettings.analytics_key``), never the admin password and
never the full server-to-server API key -- so a third party can read what's happening (attribution, payment
attempts, visits, revenue, abandoned sessions) without being able to change anything: no route here writes.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import AnalyticsCaller, Config, DbSession
from app.schemas.reports import AttemptStatsOut, AttributionOut, RevenueOut, StatsOut, VisitRow, VisitsOut
from app.schemas.sessions import AbandonedSessionsOut, TimelineItemOut
from app.services import reports, sessions

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics (read-only)"])

# ``tz`` is the caller's Date.getTimezoneOffset() so "today" and daily buckets match its local days.
TzOffset = Query(default=0, ge=-900, le=900)
HoursQuery = Query(default=6, ge=1, le=24 * 30)


@router.get("/stats", response_model=StatsOut)
def stats(db: DbSession, config: Config, caller: AnalyticsCaller):
    return reports.stats(db, config, caller.scope)


@router.get("/revenue", response_model=RevenueOut)
def revenue(db: DbSession, config: Config, caller: AnalyticsCaller, days: int = 30, tz: int = TzOffset):
    return reports.revenue_report(db, config, reports.clamp_days(days), tz, caller.scope)


@router.get("/visits", response_model=VisitsOut)
def visits(db: DbSession, caller: AnalyticsCaller, days: int = 30, tz: int = TzOffset):
    return reports.visits_report(db, reports.clamp_days(days), tz, caller.scope)


@router.get("/attribution", response_model=AttributionOut)
def attribution(db: DbSession, config: Config, caller: AnalyticsCaller, days: int = 30):
    return reports.attribution_report(db, config, days, caller.scope)


@router.get("/attempts", response_model=AttemptStatsOut)
def attempts(db: DbSession, caller: AnalyticsCaller, days: int = 30):
    return reports.attempts_report(db, days, caller.scope)


@router.get("/visits/lookup", response_model=list[VisitRow])
def visits_lookup(db: DbSession, caller: AnalyticsCaller, ip: str = Query(default="", max_length=45), days: int = 30):
    """``ip`` filters by prefix; left empty, this is just the most recent visits."""
    return reports.visits_by_ip(db, ip, days, caller.scope)


@router.get("/abandoned", response_model=AbandonedSessionsOut)
def abandoned(db: DbSession, caller: AnalyticsCaller, hours: int = HoursQuery):
    rows = sessions.abandoned_sessions(db, hours, caller.scope)
    return AbandonedSessionsOut(hours=hours, rows=rows)


@router.get("/sessions/{session_id}/timeline", response_model=list[TimelineItemOut])
def timeline(session_id: str, db: DbSession, caller: AnalyticsCaller):
    return sessions.session_timeline(db, session_id, caller.scope)
