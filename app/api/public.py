"""Endpoints used by the customer-facing checkout page. The unguessable session id is the capability."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Query, Request, Response

from app.api.deps import Config, DbSession, base_url
from app.errors import BadGateway, BadRequest
from app.models import STEPS
from app.repositories import CheckoutEventRepository, OrderRepository
from app.schemas.checkout import CompleteSessionIn, CompleteSessionOut, PublicSessionOut
from app.security import checkout_limiter, client_ip, complete_limiter
from app.services import attribution, checkout, payment_attempts
from app.services.visits import VisitContext, record_visit

router = APIRouter(prefix="/api/public", tags=["checkout page"])

VISITOR_COOKIE = "bvid"
VISITOR_COOKIE_MAX_AGE = 365 * 24 * 3600


@router.get("/brand")
def brand(config: Config):
    """Name and logo of the default store, so the admin sign-in page can show them before anyone is signed in."""
    store = config.default_store
    return {"name": store.name, "logo_url": store.settings.logo_url}


@router.get("/sessions/{session_id}", response_model=PublicSessionOut, response_model_by_alias=True)
def view_session(session_id: str, request: Request, response: Response, db: DbSession, config: Config, ref: str = ""):
    session = checkout.get_session(db, session_id)
    order = OrderRepository(db).get(session.order_id) if session.order_id else None
    visitor_id = request.cookies.get(VISITOR_COOKIE, "")
    if not visitor_id:
        visitor_id = secrets.token_hex(16)
        response.set_cookie(
            VISITOR_COOKIE,
            visitor_id,
            max_age=VISITOR_COOKIE_MAX_AGE,
            samesite="lax",
            secure=request.url.scheme == "https",
            path="/",
        )
    if session.status == "open":
        attribution.apply(session, attribution.from_query_params(request.query_params))
        record_visit(
            db,
            config,
            session,
            VisitContext(
                ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
                host=request.headers.get("host", ""),
                referrer=ref,
                visitor_id=visitor_id,
            ),
        )
    return checkout.public_view(config, session, order)


@router.post("/sessions/{session_id}/complete", response_model=CompleteSessionOut)
def place_order(session_id: str, data: CompleteSessionIn, request: Request, db: DbSession, config: Config):
    complete_limiter.hit(client_ip(request))
    store_id = checkout.get_session(db, session_id).store_id
    try:
        session, order, redirect_url, created = checkout.complete_session(
            db, config, session_id, data, base_url(request), client_ip(request)
        )
    except BadRequest as exc:
        reason = getattr(exc, "reason", None)  # only an actual processor decline carries one; validation errors don't
        if reason is not None:
            payment_attempts.record_outcome(
                store_id=store_id,
                session_id=session_id,
                outcome="declined",
                reason=reason,
                method_id=data.payment_method,
            )
        raise
    except BadGateway as exc:
        payment_attempts.record_outcome(
            store_id=store_id, session_id=session_id, outcome="error", reason=exc.message, method_id=data.payment_method
        )
        raise
    if created:
        # only card payments go through a real charge attempt that could have been declined or retried; bank
        # transfers and the test gateway always succeed trivially, so logging them would just be noise here.
        store = checkout.store_for(config, store_id).settings
        method = next((m for m in store.payment_methods if m.id == order.payment_method_id), None)
        if method and method.type == "card":
            payment_attempts.record_outcome(
                store_id=store_id, session_id=session_id, outcome="succeeded", method_id=order.payment_method_id
            )
    return CompleteSessionOut(
        order_number=order.number,
        payment_status=order.payment_status,
        payment_instructions="" if order.payment_status == "paid" else order.payment_instructions,
        success_url=checkout.build_success_url(session, order),
        redirect_url=redirect_url,
    )


@router.post("/sessions/{session_id}/steps", status_code=204)
def record_step(session_id: str, request: Request, db: DbSession, step: str = Query(...)) -> Response:
    """A checkout-form milestone reached (see ``app.models.STEPS``), for the funnel. Best effort: never blocks."""
    checkout_limiter.hit(client_ip(request))
    if step not in STEPS:
        raise BadRequest("Unknown step")
    session = checkout.get_session(db, session_id)
    if session.status == "open":
        CheckoutEventRepository(db).record(session.store_id, session_id, step)
    return Response(status_code=204)
