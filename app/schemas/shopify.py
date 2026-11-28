"""Payloads for the Shopify connector (called by the storefront theme script in the shopper's browser)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import Text200, Text300


class CartLine(BaseModel):
    """One cart line. Only ids and quantities are accepted: prices always come from Shopify, never the browser."""

    variant_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=999)


class ShopifyCartIn(BaseModel):
    items: list[CartLine] = Field(min_length=1, max_length=50)
    shop: Text200 = ""  # the shop's myshopify domain (``Shopify.shop``); identifies the store when the Origin cannot
    cart_token: Text200 = ""  # Shopify's cart token (``/cart.js`` -> ``token``); kept as a reference on the order
    # Raw utm_*/click-id params from the page the shopper checked out from (see app.services.attribution);
    # normalised server-side so the click-id -> network mapping has a single source of truth. This is "last
    # touch": the checkout-redirect.js script refreshes it as new tagged pages are seen during the visit.
    attribution: dict[str, str] = Field(default_factory=dict)
    # Same raw shape as ``attribution``, but frozen the first time checkout-redirect.js ever saw a tag on this
    # browser (its 90-day first-touch cookie) -- never overwritten after that, so it can be compared to "last touch".
    first_touch: dict[str, str] = Field(default_factory=dict)
    deep2k_anonymous_id: Text200 = ""  # window.Deep2k.anonymousId, when the store's Deep2K snippet is present
    deep2k_session_id: Text200 = ""  # window.Deep2k.sessionId
    landing_path: Text300 = ""  # the page path the shopper first landed on (captured alongside first_touch)
    # 300, matching the CheckoutSession/Order columns -- a narrower cap here would silently truncate a long
    # path before it ever reaches a column sized to hold it in full.


class ShopifyCheckoutOut(BaseModel):
    checkout_url: str


class ShopifyTestOut(BaseModel):
    ok: bool
    shop_name: str
