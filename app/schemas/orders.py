from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Text200


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    sku: str
    description: str
    image: str
    unit_amount: int
    quantity: int


class OrderEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    text: str


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    number: int
    session_id: str
    external_ref: str
    status: str
    payment_status: str
    payment_method: dict
    payment_instructions: str
    payment_reference: str
    items: list[OrderItemOut]
    currency: str
    subtotal: int
    shipping: int
    tax: int
    total: int
    customer: dict
    shipping_address: dict
    tracking_number: str
    notes: str
    metadata: dict = Field(validation_alias="meta")
    paid_at: datetime | None
    history: list[OrderEventOut]
    created_at: datetime
    updated_at: datetime


class OrderListOut(BaseModel):
    data: list[OrderOut]
    has_more: bool = False


class OrderUpdateIn(BaseModel):
    """Partial update. Fields that are omitted are left untouched."""

    status: Literal["pending", "processing", "shipped", "completed", "cancelled", "refunded"] | None = None
    payment_status: Literal["pending", "paid", "failed", "refunded"] | None = None
    payment_reference: Text200 | None = None
    tracking_number: Text200 | None = None
    notes: str | None = Field(default=None, max_length=5000)
    notify: bool = True  # False = don't email the customer about this change
