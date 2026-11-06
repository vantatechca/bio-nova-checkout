"""Payment gateways.

A gateway decides the payment status of a freshly placed order. To add a payment type, write a class here
(charge it, verify the result server-side, return ``PaymentResult`` or raise ``BadRequest``) and register it for a new
``PaymentMethod.type``. **Never accept or store raw card numbers in this app**: cards are tokenized by the processor's
own fields in the customer's browser, and only the token comes through here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings
from app.errors import BadRequest
from app.models import CheckoutSession, PaymentStatus
from app.schemas.checkout import AddressIn, CustomerIn
from app.schemas.settings import PaymentMethod, StoreSettings
from app.services import client_payment_api


def card_available(store: StoreSettings) -> bool:
    """Whether customers may pay by card right now.

    It needs a provider and the client's API configured. The fake "mock" provider (which approves any test card) is
    additionally refused on a public https site, so a leftover test setup can never mark real orders paid.
    """
    if not store.card_payments_ready:
        return False
    settings = get_settings()
    if store.card_provider == "mock" and (settings.public_url or "").startswith("https://"):
        return settings.allow_test_card_provider
    return True


@dataclass(frozen=True)
class PaymentRequest:
    """Everything a gateway may need beyond the session itself."""

    store: StoreSettings
    customer: CustomerIn
    address: AddressIn
    token: str = ""  # single-use card token from the processor's fields (card payments only)
    return_url: str = ""  # where the client's payment page sends the customer back to (redirect flow)


@dataclass(frozen=True)
class PaymentResult:
    status: str
    reference: str = ""  # e.g. the processor's charge id
    redirect_url: str = ""  # redirect flow: send the customer here to pay; the client marks the order paid afterwards


class PaymentGateway(Protocol):
    def process(self, method: PaymentMethod, session: CheckoutSession, request: PaymentRequest) -> PaymentResult:
        """Returns the order's initial payment status."""


class OfflineGateway:
    """Zelle, Interac e-Transfer, bank transfer, cash on delivery: an admin marks the order paid by hand."""

    def process(self, method: PaymentMethod, session: CheckoutSession, request: PaymentRequest) -> PaymentResult:
        return PaymentResult(PaymentStatus.PENDING)


class TestGateway:
    """Marks the order paid immediately without charging anything (development only)."""

    __test__ = False  # not a pytest class

    def process(self, method: PaymentMethod, session: CheckoutSession, request: PaymentRequest) -> PaymentResult:
        return PaymentResult(PaymentStatus.PAID)


class CardGateway:
    """Takes a card payment through the client's own payment API (and therefore the client's processor).

    Embedded form (provider ``embed`` and others): we pass the card token and get ``succeeded`` / ``declined`` back.
    Redirect (provider ``redirect``): we ask for a payment page, the customer pays there, and the client marks the order paid.
    """

    def process(self, method: PaymentMethod, session: CheckoutSession, request: PaymentRequest) -> PaymentResult:
        store = request.store
        if not card_available(store):
            raise BadRequest("Card payments aren't available right now. Please choose another payment method.")
        redirect = store.card_provider == "redirect"
        if not redirect and not request.token:
            raise BadRequest("Please enter your card details")
        payload = {
            "type": "create_payment" if redirect else "charge",
            "reference": session.id,
            "order_ref": session.external_ref,
            "amount": session.total,
            "currency": session.currency,
            "description": f"Order from {store.store_name}",
            "customer": request.customer.model_dump(),
            "shipping_address": request.address.model_dump(),
            "items": [
                {"name": i["name"], "sku": i.get("sku", ""), "quantity": i["quantity"], "unit_amount": i["unit_amount"]}
                for i in session.items
            ],
        }
        if redirect:
            payload["return_url"] = payload["cancel_url"] = request.return_url
            hosted = client_payment_api.create_payment(store, payload, idempotency_key=session.id)
            return PaymentResult(PaymentStatus.PENDING, hosted.reference, redirect_url=hosted.redirect_url)
        payload["token"] = request.token
        result = client_payment_api.charge(store, payload, idempotency_key=session.id)
        return PaymentResult(PaymentStatus.PAID, result.reference)


GATEWAYS: dict[str, PaymentGateway] = {"offline": OfflineGateway(), "test": TestGateway(), "card": CardGateway()}


def process_payment(method: PaymentMethod, session: CheckoutSession, request: PaymentRequest) -> PaymentResult:
    return GATEWAYS[method.type].process(method, session, request)
