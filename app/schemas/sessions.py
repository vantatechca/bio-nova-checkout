from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AbandonedSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    store_id: int
    created_at: datetime
    viewed_at: datetime | None
    customer_name: str
    customer_email: str
    total: int
    currency: str
    steps: list[str]


class AbandonedSessionsOut(BaseModel):
    hours: int
    rows: list[AbandonedSessionOut]


class TimelineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    kind: str
    text: str


# ---------------------------------------------------------------- read-only analytics (no customer PII)
class AnalyticsAbandonedSessionOut(BaseModel):
    """Same as ``AbandonedSessionOut`` but without the customer's name/email -- for the read-only analytics key."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    store_id: int
    created_at: datetime
    viewed_at: datetime | None
    total: int
    currency: str
    steps: list[str]


class AnalyticsAbandonedSessionsOut(BaseModel):
    hours: int
    rows: list[AnalyticsAbandonedSessionOut]
    has_more: bool = False
