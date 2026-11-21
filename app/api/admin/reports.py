from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import Config, DbSession, StoreScope
from app.schemas.reports import AttemptStatsOut, AttributionOut, RevenueOut, StatsOut, VisitRow, VisitsOut
from app.services import reports

router = APIRouter(prefix="/api/admin", tags=["admin: reports"])

# ``tz`` is the browser's Date.getTimezoneOffset() so "today" and daily buckets match the admin's local days.
TzOffset = Query(default=0, ge=-900, le=900)


@router.get("/stats", response_model=StatsOut)
def stats(db: DbSession, config: Config, store: StoreScope):
    return reports.stats(db, config, store)


@router.get("/revenue", response_model=RevenueOut)
def revenue(db: DbSession, config: Config, store: StoreScope, days: int = 30, tz: int = TzOffset):
    return reports.revenue_report(db, config, reports.clamp_days(days), tz, store)


@router.get("/visits", response_model=VisitsOut)
def visits(db: DbSession, store: StoreScope, days: int = 30, tz: int = TzOffset):
    return reports.visits_report(db, reports.clamp_days(days), tz, store)


@router.get("/attribution", response_model=AttributionOut)
def attribution(db: DbSession, config: Config, store: StoreScope, days: int = 30):
    return reports.attribution_report(db, config, days, store)


@router.get("/attempts", response_model=AttemptStatsOut)
def attempts(db: DbSession, store: StoreScope, days: int = 30):
    return reports.attempts_report(db, days, store)


@router.get("/visits/lookup", response_model=list[VisitRow])
def visits_lookup(db: DbSession, store: StoreScope, ip: str = Query(min_length=1, max_length=45), days: int = 30):
    return reports.visits_by_ip(db, ip, days, store)
