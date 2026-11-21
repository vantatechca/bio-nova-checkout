from __future__ import annotations

from pydantic import BaseModel


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


class VisitsOut(BaseModel):
    days: int
    views: int
    visitors: int
    funnel: Funnel
    daily: list[DailyVisits]
    devices: list[LabelCount]
    referrers: list[LabelCount]
