"""Public endpoint called by the Shopify theme script when a shopper clicks "Checkout"."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.api.deps import Config, DbSession, base_url
from app.errors import AppError
from app.schemas.shopify import ShopifyCartIn
from app.security import client_ip, shopify_limiter
from app.services import checkout, shopify

router = APIRouter(prefix="/api/shopify", tags=["shopify"])


def _cors_headers(request: Request, config: Config) -> dict[str, str]:
    """Only the configured storefront may read responses from a browser; everyone else gets none."""
    origin = request.headers.get("origin", "")
    headers = {"Vary": "Origin"}
    if origin and origin in shopify.allowed_origins(config.store):
        headers["Access-Control-Allow-Origin"] = origin
    return headers


@router.options("/checkout", include_in_schema=False)
def preflight(request: Request, config: Config) -> Response:
    headers = _cors_headers(request, config)
    if "Access-Control-Allow-Origin" in headers:
        headers.update(
            {
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "600",
            }
        )
    return Response(status_code=204, headers=headers)


@router.post("/checkout")
def checkout_from_cart(data: ShopifyCartIn, request: Request, db: DbSession, config: Config) -> JSONResponse:
    """Turns a Shopify cart into a checkout session (prices come from Shopify) and returns the page to redirect to."""
    headers = _cors_headers(request, config)
    try:
        shopify_limiter.hit(client_ip(request))
        session = shopify.create_checkout_from_cart(db, config, data.items, data.cart_token)
    except AppError as exc:  # answered here (not re-raised) so the error carries the CORS headers the browser needs
        return JSONResponse({"error": exc.message}, status_code=exc.status_code, headers=headers)
    return JSONResponse(
        {"checkout_url": checkout.session_out(session, base_url(request)).checkout_url}, headers=headers
    )
