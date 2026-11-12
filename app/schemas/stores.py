"""Payloads for managing the stores connected to this checkout."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import Text100


class StoreCreateIn(BaseModel):
    name: Text100 = Field(min_length=1)
    copy_from: int | None = None  # id of a store whose card/payment, shipping and branding settings to start from


class StoreActiveIn(BaseModel):
    active: bool


class StoreOut(BaseModel):
    id: int
    slug: str
    name: str
    active: bool
    logo_url: str
    store_url: str
    shopify_domain: str
    card_ready: bool
    orders: int
