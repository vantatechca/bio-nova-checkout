"""Payloads for creating checkout sessions (store API) and completing them (customer page)."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.schemas.common import Text20, Text40, Text100, Text200, Text300, Text500, Text2000


# ---------------------------------------------------------------- inputs
class LineItemIn(BaseModel):
    name: Text200 = Field(min_length=1)
    unit_amount: StrictInt = Field(ge=0, description="Price per unit in minor units (e.g. cents)")
    quantity: StrictInt = Field(default=1, ge=1, le=999)
    sku: Text100 = ""
    description: Text300 = ""
    image: str = ""

    @field_validator("image")
    @classmethod
    def _http_image_only(cls, v: str) -> str:
        return v.strip() if urlparse(v.strip()).scheme in ("http", "https") else ""


class CustomerIn(BaseModel):
    name: Text200 = ""
    email: Text200 = ""
    phone: Text40 = ""


class AddressIn(BaseModel):
    line1: Text200 = ""
    line2: Text200 = ""
    city: Text100 = ""
    state: Text100 = ""
    postal_code: Text20 = ""
    country: Text100 = ""


class CreateSessionIn(BaseModel):
    items: list[LineItemIn] = Field(min_length=1, max_length=100)
    currency: str | None = None
    shipping_amount: StrictInt | None = Field(default=None, ge=0)
    tax_amount: StrictInt | None = Field(default=None, ge=0)
    customer: CustomerIn = Field(default_factory=CustomerIn)
    success_url: Text2000
    cancel_url: Text2000 = ""
    external_ref: Text200 = ""  # your store's own cart / order id, echoed back in webhooks
    metadata: dict = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _small_metadata(cls, v: dict) -> dict:
        import json

        if len(json.dumps(v)) > 5000:
            raise ValueError("metadata is too large (max 5000 characters)")
        return v


class CompleteSessionIn(BaseModel):
    customer: CustomerIn = Field(default_factory=CustomerIn)
    shipping_address: AddressIn = Field(default_factory=AddressIn)
    payment_method: str = ""
    card_token: Text500 = ""  # single-use token from the processor's card fields (never the card number)


# ---------------------------------------------------------------- outputs
class SessionOut(BaseModel):
    """Session as returned to the store (includes the link to send the customer to)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    currency: str
    items: list[dict]
    subtotal: int
    shipping: int
    tax: int
    total: int
    customer: dict
    success_url: str
    cancel_url: str
    external_ref: str
    metadata: dict = Field(validation_alias="meta")
    order_id: str | None
    viewed_at: datetime | None
    created_at: datetime
    expires_at: datetime
    checkout_url: str = ""


class PaymentMethodPublic(BaseModel):
    id: str
    label: str
    type: str  # "offline" | "test" | "card"
    instructions: str


class CardPublic(BaseModel):
    """What the checkout page needs to show the processor's card fields (the key is the *publishable* one)."""

    provider: str
    public_key: str
    form_url: str = ""  # provider "embed": the client-hosted card form to show in an iframe


class NavLinkPublic(BaseModel):
    label: str
    url: str


class Branding(BaseModel):
    """Storefront look-and-feel details for the checkout page header."""

    logo_url: str
    store_url: str
    nav_links: list[NavLinkPublic]
    notice: str


class PublicSessionOut(BaseModel):
    """What the customer-facing checkout page may see (no secrets)."""

    id: str
    status: str
    store_name: str = Field(serialization_alias="storeName")
    currency: str
    items: list[dict]
    subtotal: int
    shipping: int
    tax: int
    total: int
    customer: dict
    cancel_url: str
    success_url: str | None
    order_number: int | None
    payment_instructions: str | None
    payment_status: str | None
    payment_url: str = ""  # redirect card flow, not yet paid: where the customer can go on paying
    payment_methods: list[PaymentMethodPublic] = Field(serialization_alias="paymentMethods")
    card: CardPublic | None = None
    branding: Branding


class CompleteSessionOut(BaseModel):
    order_number: int
    payment_status: str
    payment_instructions: str
    success_url: str
    redirect_url: str = ""  # redirect card flow: send the customer to the client's payment page
