from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import Config, DbSession
from app.schemas.reports import RevenueOut, StatsOut, VisitsOut
from app.services import reports

router = APIRouter(prefix="/api/admin", tags=["admin: reports"])

# ``tz`` is the browser's Date.getTimezoneOffset() so "today" and daily buckets match the admin's local days.
TzOffset = Query(default=0, ge=-900, le=900)


@router.get("/stats", response_model=StatsOut)
def stats(db: DbSession, config: Config):
    return reports.stats(db, config)


@router.get("/revenue", response_model=RevenueOut)
def revenue(db: DbSession, config: Config, days: int = 30, tz: int = TzOffset):
    return reports.revenue_report(db, config, reports.clamp_days(days), tz)


@router.get("/visits", response_model=VisitsOut)
def visits(db: DbSession, days: int = 30, tz: int = TzOffset):
    return reports.visits_report(db, reports.clamp_days(days), tz)
