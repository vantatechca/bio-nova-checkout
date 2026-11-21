"""Shopify connector.

The storefront theme sends the shopper's cart (variant ids + quantities). We never trust prices from the
browser: they are looked up from Shopify's Storefront API, then a normal checkout session is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import BadGateway, BadRequest
from app.models import CheckoutSession
from app.schemas.checkout import CreateSessionIn, LineItemIn
from app.schemas.shopify import CartLine
from app.services import checkout
from app.services.config import AppConfig, StoreRecord

# Shopify serves requests for retired versions with the oldest supported one, so this keeps working over time.
STOREFRONT_API_VERSION = "2026-04"
TIMEOUT_SECONDS = 10

VARIANT_QUERY = """
query Variants($ids: [ID!]!) {
  nodes(ids: $ids) {
    ... on ProductVariant {
      id title sku availableForSale
      price { amount currencyCode }
      image { url }
      product { title featuredImage { url } }
    }
  }
}"""
SHOP_QUERY = "{ shop { name } }"


@dataclass(frozen=True)
class Variant:
    id: int
    title: str
    product_title: str
    sku: str
    available: bool
    unit_amount: int  # minor units
    currency: str
    image: str

    @property
    def is_default_variant(self) -> bool:
        return self.title.strip().lower() == "default title"

    @property
    def display_name(self) -> str:
        return self.product_title if self.is_default_variant else f"{self.product_title} — {self.title}"


def graphql_url(domain: str) -> str:
    base = get_settings().shopify_api_base_url or f"https://{domain}"
    return f"{base.rstrip('/')}/api/{STOREFRONT_API_VERSION}/graphql.json"


class ShopifyClient:
    """Minimal Storefront API client (read-only product data)."""

    def __init__(self, domain: str, storefront_token: str) -> None:
        self.domain, self.token = domain, storefront_token

    def _query(self, query: str, variables: dict | None = None) -> dict:
        try:
            response = httpx.post(
                graphql_url(self.domain),
                json={"query": query, "variables": variables or {}},
                headers={"X-Shopify-Storefront-Access-Token": self.token, "Content-Type": "application/json"},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise BadGateway("Could not reach Shopify, please try again") from exc
        if response.status_code in (401, 403):
            raise BadGateway("Shopify rejected the Storefront access token — check it in Settings")
        if response.status_code == 404:
            raise BadGateway("Shopify shop not found — check the shop domain in Settings")
        if response.status_code >= 400:
            raise BadGateway(f"Shopify returned an error ({response.status_code})")
        try:
            body = response.json()
        except ValueError as exc:
            raise BadGateway("Shopify returned an unreadable response") from exc
        if body.get("errors") or "data" not in body:
            raise BadGateway("Shopify could not look up the cart items")
        return body["data"]

    def shop_name(self) -> str:
        return self._query(SHOP_QUERY)["shop"]["name"]

    def variants(self, variant_ids: list[int]) -> dict[int, Variant]:
        gids = [f"gid://shopify/ProductVariant/{vid}" for vid in variant_ids]
        found: dict[int, Variant] = {}
        for node in self._query(VARIANT_QUERY, {"ids": gids})["nodes"]:
            if not node:  # unknown / deleted variant
                continue
            vid = int(node["id"].rsplit("/", 1)[1])
            product = node.get("product") or {}
            image = (node.get("image") or product.get("featuredImage") or {}).get("url") or ""
            found[vid] = Variant(
                id=vid,
                title=node.get("title") or "",
                product_title=product.get("title") or "Item",
                sku=node.get("sku") or "",
                available=bool(node.get("availableForSale")),
                unit_amount=int((Decimal(node["price"]["amount"]) * 100).to_integral_value()),
                currency=node["price"]["currencyCode"],
                image=image,
            )
        return found


def resolve_store(config: AppConfig, origin: str = "", shop: str = "") -> StoreRecord:
    """Works out which store a browser request is for: by the page's ``Origin``, else by the ``shop`` domain
    the theme script reports. With a single active store nothing needs to identify it."""
    candidates = config.stores_for_origin(origin) if origin else []
    if not candidates and shop:
        candidates = config.stores_for_shop(shop)
    if not candidates:
        active = [s for s in config.stores if s.active]
        if len(active) == 1:  # a single store needs no identifying (the browser still can't read the answer via CORS)
            candidates = active
        elif origin or shop:
            raise BadRequest("This website isn't connected to a store here. Add it under Stores → Settings.")
        else:
            raise BadRequest("Couldn't tell which store this cart belongs to")
    if len(candidates) > 1:
        raise BadRequest("More than one store matches this website; each store needs its own domain")
    return candidates[0]


def create_checkout_from_cart(
    db: Session, record: StoreRecord, lines: list[CartLine], cart_token: str = ""
) -> CheckoutSession:
    store = record.settings
    if not (store.shopify_domain and store.shopify_storefront_token):
        raise BadRequest("Shopify isn't connected yet — add the shop domain and Storefront token in Settings")
    if not store.store_url:
        raise BadRequest("Set your Store website under Settings → Branding first")

    quantities: dict[int, int] = {}
    for line in lines:  # the same variant on two lines (e.g. different properties) becomes one line
        quantities[line.variant_id] = min(quantities.get(line.variant_id, 0) + line.quantity, 999)

    variants = ShopifyClient(store.shopify_domain, store.shopify_storefront_token).variants(list(quantities))
    items: list[LineItemIn] = []
    currency = ""
    for variant_id, quantity in quantities.items():
        variant = variants.get(variant_id)
        if variant is None:
            raise BadRequest("An item in your cart is no longer available. Please review your cart.")
        if not variant.available:
            raise BadRequest(f"“{variant.display_name}” is out of stock. Please review your cart.")
        currency = currency or variant.currency
        if variant.currency != currency:
            raise BadRequest("Your cart mixes currencies, which isn't supported")
        items.append(
            LineItemIn(
                name=variant.display_name[:200],
                unit_amount=variant.unit_amount,
                quantity=quantity,
                sku=variant.sku[:100],
                description="" if variant.is_default_variant else variant.title[:300],
                image=variant.image,
            )
        )

    storefront = store.store_url.rstrip("/")
    return checkout.create_session(
        db,
        record,
        CreateSessionIn(
            items=items,
            currency=currency,
            success_url=storefront,
            cancel_url=f"{storefront}/cart",
            external_ref=f"shopify:{cart_token}"[:200] if cart_token else "shopify",
            metadata={"source": "shopify"},
        ),
    )
