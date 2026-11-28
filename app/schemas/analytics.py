"""Output shapes for the read-only analytics API (see ``app.api.analytics``).

Deliberately a reduced view of the admin's own ``OrderOut``: no customer name/email/phone, no shipping
address, no raw IP, no internal notes or payment reference -- a bot reading these doesn't need them, and
handing them out would be a real privacy exposure, not just an inconvenience.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.orders import OrderItemOut


class AnalyticsOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    number: int
    store_id: int
    session_id: str
    external_ref: str
    status: str
    payment_status: str
    items: list[OrderItemOut]
    currency: str
    subtotal: int
    shipping: int
    tax: int
    total: int
    utm_source: str
    utm_medium: str
    utm_campaign: str
    utm_content: str
    utm_term: str
    click_provider: str
    click_id: str
    order_country: str  # country only -- the raw order_ip is not exposed here
    risk_flags: dict
    metadata: dict = Field(validation_alias="meta")
    paid_at: datetime | None
    created_at: datetime


class AnalyticsOrderListRow(BaseModel):
    """One row of the read-only orders feed (see app.services.orders.analytics_orders). Customer contact info
    is masked, never returned raw or omitted outright -- enough to recognise a repeat customer, not enough to
    contact them."""

    number: int
    store_id: int
    created_at: datetime
    status: str
    payment_status: str
    total: int
    currency: str
    utm_source: str
    utm_medium: str
    utm_campaign: str
    utm_content: str
    utm_term: str
    click_provider: str
    click_id: str
    customer_email_masked: str
    customer_phone_masked: str


class AnalyticsOrderListOut(BaseModel):
    rows: list[AnalyticsOrderListRow]
    has_more: bool
