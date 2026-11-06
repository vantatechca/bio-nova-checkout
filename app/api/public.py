"""Endpoints used by the customer-facing checkout page. The unguessable session id is the capability."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import Config, DbSession, base_url
from app.repositories import OrderRepository
from app.schemas.checkout import CompleteSessionIn, CompleteSessionOut, PublicSessionOut
from app.security import client_ip
from app.services import checkout
from app.services.visits import VisitContext, record_visit

router = APIRouter(prefix="/api/public", tags=["checkout page"])


@router.get("/sessions/{session_id}", response_model=PublicSessionOut, response_model_by_alias=True)
def view_session(session_id: str, request: Request, db: DbSession, config: Config, ref: str = ""):
    session = checkout.get_session(db, session_id)
    order = OrderRepository(db).get(session.order_id) if session.order_id else None
    if session.status == "open":
        record_visit(
            db,
            config,
            session,
            VisitContext(
                ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
                host=request.headers.get("host", ""),
                referrer=ref,
            ),
        )
    return checkout.public_view(config, session, order)


@router.post("/sessions/{session_id}/complete", response_model=CompleteSessionOut)
def place_order(session_id: str, data: CompleteSessionIn, request: Request, db: DbSession, config: Config):
    session, order, redirect_url = checkout.complete_session(db, config, session_id, data, base_url(request))
    return CompleteSessionOut(
        order_number=order.number,
        payment_status=order.payment_status,
        payment_instructions="" if order.payment_status == "paid" else order.payment_instructions,
        success_url=checkout.build_success_url(session, order),
        redirect_url=redirect_url,
    )
