from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    views_excluding_internal: int
    visitors_excluding_internal: int
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
    is_internal: bool
    # The same salted hash record_visit() dedupes/counts unique visitors by (never the IP) -- so a caller can
    # tell "the same visitor came back" apart from "a different visitor," without it being reversible to an IP.
    visitor_id: str = Field(validation_alias="visitor")


class ArrivalRow(BaseModel):
    """One checkout-page arrival breakdown row: unique visitors (internal traffic already excluded), by local
    day, store, campaign, search term, whether an ad click id was present, device and city."""

    date: str
    store_id: int
    utm_campaign: str
    utm_term: str
    has_click_id: bool
    device: str
    city: str
    arrivals: int
    views: int


class SessionsVsArrivalsRow(BaseModel):
    """"Pressed Checkout" (sessions_created) vs "arrived" (actually opened), per local day/store/campaign/term/
    click-id-presence -- internal/test sessions already excluded."""

    date: str
    store_id: int
    utm_campaign: str
    utm_term: str
    has_click_id: bool
    sessions_created: int
    arrived: int


class ArrivalsOut(BaseModel):
    days: int
    rows: list[ArrivalRow]
    has_more: bool
    sessions_vs_arrivals: list[SessionsVsArrivalsRow]
    sessions_has_more: bool


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
