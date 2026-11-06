"""HTTP layer: routers are thin and delegate to ``app.services``."""

from fastapi import APIRouter

from app.api import admin, health, public, shopify, store

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(store.router)
api_router.include_router(public.router)
api_router.include_router(shopify.router)
api_router.include_router(admin.router)
