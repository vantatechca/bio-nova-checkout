"""Server-to-server API used by the store backend (authenticated with the API key)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import ApiStore, Config, DbSession, base_url
from app.repositories import OrderRepository
from app.schemas.checkout import CreateSessionIn, SessionOut
from app.schemas.orders import OrderListOut, OrderOut, OrderUpdateIn
from app.services import checkout, orders

router = APIRouter(prefix="/api/v1", tags=["store api"])


@router.post("/checkout/sessions", response_model=SessionOut, status_code=201)
def create_checkout_session(data: CreateSessionIn, request: Request, db: DbSession, store: ApiStore):
    """Create a checkout session, then redirect the customer to the returned ``checkout_url``."""
    session = checkout.create_session(db, store, data)
    return checkout.session_out(session, base_url(request))


@router.get("/checkout/sessions/{session_id}", response_model=SessionOut)
def get_checkout_session(session_id: str, request: Request, db: DbSession, store: ApiStore):
    return checkout.session_out(checkout.get_session(db, session_id, store.id), base_url(request))


@router.get("/orders", response_model=OrderListOut)
def list_orders(db: DbSession, store: ApiStore, external_ref: str | None = None):
    rows, has_more = OrderRepository(db, store.id).list(external_ref=external_ref, limit=100)
    return OrderListOut(data=rows, has_more=has_more)


@router.get("/orders/{key}", response_model=OrderOut)
def get_order(key: str, db: DbSession, store: ApiStore):
    return orders.get_order(db, key, store.id)


@router.patch("/orders/{key}", response_model=OrderOut)
def update_order(key: str, data: OrderUpdateIn, db: DbSession, config: Config, store: ApiStore):
    return orders.update_order(db, config, key, data, store.id)
