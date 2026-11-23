from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TabCounts(BaseModel):
    pending: int
    paid: int
    failed: int


class StatsOut(BaseModel):
    total_orders: int
    by_status: dict[str, int]
    paid_revenue: int
    currency: str
    counts: TabCounts


class DailyRevenue(BaseModel):
    date: str
    amount: int
    orders: int


class MethodRevenue(BaseModel):
    label: str
    orders: int
    amount: int


class RevenueOut(BaseModel):
    currency: str
    days: int
    excluded_other_currency: int
    today: int
    last7: int
    last30: int
    all_time: int
    period_total: int
    period_orders: int
    avg_order: int
    awaiting_payment: int
    awaiting_count: int
    refunded: int
    refunded_count: int
    daily: list[DailyRevenue]
    by_method: list[MethodRevenue]


class DailyVisits(BaseModel):
    date: str
    views: int
    visitors: int


class LabelCount(BaseModel):
    label: str
    count: int


class Funnel(BaseModel):
    created: int
    viewed: int
    ordered: int
    conversion: float
    steps: list[LabelCount]


class VisitsOut(BaseModel):
    days: int
    views: int
    visitors: int
    funnel: Funnel
    daily: list[DailyVisits]
    devices: list[LabelCount]
    referrers: list[LabelCount]


class CampaignRow(BaseModel):
    campaign: str
    sessions: int
    viewed: int
    orders: int
    revenue: int
    conversion: float


class AttributionOut(BaseModel):
    days: int
    currency: str
    rows: list[CampaignRow]


class VisitRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    ip: str
    country: str
    city: str
    device: str
    referrer: str


class AttemptRow(BaseModel):
    reason: str
    count: int


class RecentAttempt(BaseModel):
    at: datetime
    store_id: int
    session_id: str
    outcome: str
    reason: str
    attempt_no: int


class AttemptStatsOut(BaseModel):
    days: int
    total: int
    declined: int
    error: int
    recovered: int
    by_reason: list[AttemptRow]
    recent: list[RecentAttempt]
    recent_has_more: bool = False
