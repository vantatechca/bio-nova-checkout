"""Admin API. Everything except ``/login`` requires a valid admin token."""

from fastapi import APIRouter

from app.api.admin import auth, card, email, orders, reports, settings, shopify
from app.api.deps import AdminAuth

router = APIRouter()
router.include_router(auth.router)  # public: it issues the token

protected = APIRouter(dependencies=[AdminAuth])
for module in (orders, reports, email, settings, shopify, card):
    protected.include_router(module.router)
router.include_router(protected)
