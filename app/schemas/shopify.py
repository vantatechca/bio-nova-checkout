"""Payloads for the Shopify connector (called by the storefront theme script in the shopper's browser)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import Text200


class CartLine(BaseModel):
    """One cart line. Only ids and quantities are accepted: prices always come from Shopify, never the browser."""

    variant_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=999)


class ShopifyCartIn(BaseModel):
    items: list[CartLine] = Field(min_length=1, max_length=50)
    shop: Text200 = ""  # the shop's myshopify domain (``Shopify.shop``); identifies the store when the Origin cannot
    cart_token: Text200 = ""  # Shopify's cart token (``/cart.js`` -> ``token``); kept as a reference on the order
    # Raw utm_*/click-id params from the page the shopper checked out from (see app.services.attribution);
    # normalised server-side so the click-id -> network mapping has a single source of truth.
    attribution: dict[str, str] = Field(default_factory=dict)


class ShopifyCheckoutOut(BaseModel):
    checkout_url: str


class ShopifyTestOut(BaseModel):
    ok: bool
    shop_name: str
