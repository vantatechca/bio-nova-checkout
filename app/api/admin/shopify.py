from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Config
from app.errors import BadRequest
from app.schemas.shopify import ShopifyTestOut
from app.services.shopify import ShopifyClient

router = APIRouter(prefix="/api/admin/shopify", tags=["admin: shopify"])


@router.post("/test", response_model=ShopifyTestOut)
def test_connection(config: Config):
    """Checks the saved shop domain and Storefront token by asking Shopify for the shop's name."""
    store = config.store
    if not (store.shopify_domain and store.shopify_storefront_token):
        raise BadRequest("Enter and save the shop domain and Storefront token first")
    return ShopifyTestOut(
        ok=True, shop_name=ShopifyClient(store.shopify_domain, store.shopify_storefront_token).shop_name()
    )
