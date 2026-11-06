"""Pure-logic tests (no database)."""

from datetime import UTC, datetime

import pytest

from app.models import Order, OrderItem
from app.schemas.checkout import AddressIn, CustomerIn
from app.schemas.settings import PaymentMethod, StoreSettings
from app.services.checkout import fill_template
from app.services.emails import render_email
from app.services.money import format_money
from app.services.payments import PaymentRequest, process_payment
from app.services.reports import day_range, local_day, local_day_start
from app.services.visits import device_of, referrer_host
from app.services.webhooks import sign


@pytest.mark.parametrize(
    "minor,currency,expected",
    [
        (5000, "USD", "$50.00"),
        (123456, "usd", "$1,234.56"),
        (5, "CAD", "CA$0.05"),
        (999, "EUR", "€9.99"),
        (1000, "CHF", "10.00 CHF"),
    ],
)
def test_format_money(minor, currency, expected):
    assert format_money(minor, currency) == expected


def test_fill_template_substitutes_known_placeholders_only():
    assert fill_template("Pay {total} for #{order} {unknown}", total="$5.00", order=7) == "Pay $5.00 for #7 {unknown}"


@pytest.mark.parametrize(
    "ua,device",
    [
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17) Mobile", "mobile"),
        ("Mozilla/5.0 (Linux; Android 14)", "mobile"),
        ("Mozilla/5.0 (iPad; CPU OS 17)", "tablet"),
        ("Mozilla/5.0 (Windows NT 10.0) Chrome/120", "desktop"),
        ("Googlebot/2.1", "bot"),
        ("Slackbot-LinkExpanding", "bot"),
        ("facebookexternalhit link preview", "bot"),
    ],
)
def test_device_detection(ua, device):
    assert device_of(ua) == device


def test_referrer_host_ignores_own_host_and_garbage():
    assert referrer_host("https://shop.test/cart?x=1", "checkout.example.com") == "shop.test"
    assert referrer_host("https://checkout.example.com/x", "checkout.example.com") == ""
    assert referrer_host("", "x") == "" and referrer_host("not a url", "x") == ""


def test_local_day_helpers_follow_js_timezone_offsets():
    moment = datetime(2026, 11, 5, 1, 30, tzinfo=UTC)
    assert local_day(moment, 0) == "2026-11-05"
    assert local_day(moment, 300) == "2026-11-04"  # UTC-5 (JS offset is +300)
    assert local_day(moment, -540) == "2026-11-05"  # UTC+9
    assert local_day_start("2026-11-04", 300) == datetime(2026, 11, 4, 5, 0, tzinfo=UTC)
    days = day_range(3, 0, moment)
    assert days == ["2026-11-03", "2026-11-04", "2026-11-05"]


def test_payment_gateways():
    request = PaymentRequest(store=StoreSettings(), customer=CustomerIn(), address=AddressIn())
    assert process_payment(PaymentMethod(id="zelle", type="offline"), None, request).status == "pending"
    assert process_payment(PaymentMethod(id="t", type="test"), None, request).status == "paid"


def test_card_gateway_refuses_to_run_until_configured_and_never_without_a_token():
    from app.errors import BadRequest

    method = PaymentMethod(id="card", type="card")
    unconfigured = PaymentRequest(store=StoreSettings(), customer=CustomerIn(), address=AddressIn(), token="tok_1")
    with pytest.raises(BadRequest, match="aren't available"):
        process_payment(method, None, unconfigured)
    configured = StoreSettings(cardProvider="mock", clientApiUrl="https://client.example/charge")
    with pytest.raises(BadRequest, match="card details"):
        process_payment(method, None, PaymentRequest(store=configured, customer=CustomerIn(), address=AddressIn()))


def test_webhook_signature_format():
    sig = sign("secret", "{}")
    assert sig.startswith("sha256=") and len(sig) == 7 + 64 and sig == sign("secret", "{}") != sign("other", "{}")


def test_store_settings_normalise_and_validate():
    assert StoreSettings(currency=" cad ").currency == "CAD"
    assert StoreSettings(allowedDomains=" A.com, b.org ,").allowed_domain_list == ["a.com", "b.org"]
    with pytest.raises(ValueError):
        StoreSettings(taxRatePercent=101)


def _order(**overrides) -> Order:
    fields = {
        "number": 1001,
        "public_id": "ord_x",
        "session_id": "cs_x",
        "status": "pending",
        "payment_status": "pending",
        "payment_method_id": "interac",
        "payment_method_label": "Interac e-Transfer",
        "payment_instructions": "Send $50.00 ...",
        "payment_reference": "",
        "currency": "USD",
        "subtotal": 5000,
        "shipping": 0,
        "tax": 0,
        "total": 5000,
        "customer_name": "Ada",
        "customer_email": "ada@x.co",
        "customer_phone": "",
        "ship_line1": "1",
        "ship_city": "T",
        "ship_postal_code": "1",
        "ship_country": "CA",
        "tracking_number": "",
        "notes": "",
    }
    fields.update(overrides)
    return Order(items=[OrderItem(name="Shirt", unit_amount=2500, quantity=2)], **fields)


def test_email_templates():
    subject, body = render_email("confirmation", _order(), "Acme")
    assert (
        subject == "Order #1001 received - Acme"
        and "Send $50.00" in body
        and "Hi Ada" in body
        and "2 x Shirt - $50.00" in body
    )
    _, paid_body = render_email("confirmation", _order(payment_status="paid"), "Acme")
    assert "payment has been received" in paid_body and "Send $50.00" not in paid_body
    assert "Tracking number: T1" in render_email("shipped", _order(tracking_number="T1"), "Acme")[1]
    assert "ada@x.co" in render_email("admin", _order(), "Acme")[1]
    with pytest.raises(ValueError):
        render_email("nope", _order(), "Acme")
