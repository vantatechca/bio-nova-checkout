from email import message_from_string

from app.models import Order, OrderItem
from app.schemas.settings import SmtpSettings
from app.services import smtp as smtp_module
from app.services.email_html import render_html


def make_order(**fields) -> Order:
    order = Order(
        number=1042,
        customer_name="Ada <script>alert(1)</script>",
        customer_email="ada@example.com",
        currency="USD",
        subtotal=3999,
        shipping=895,
        tax=0,
        total=4894,
        payment_method_label="Credit card",
        payment_status="pending",
        payment_instructions="",
        tracking_number="1Z999",
        ship_line1="1 Main St",
        ship_city="San Jose",
        ship_state="CA",
        ship_postal_code="95113",
        ship_country="United States",
        **fields,
    )
    order.items = [OrderItem(name="BPC-157 <b>", unit_amount=3999, quantity=1, description="", image="")]
    return order


class TestHtmlEmails:
    def test_every_type_renders_with_totals_and_escapes_input(self):
        for kind in ("confirmation", "paid", "shipped", "cancelled", "admin"):
            html = render_html(kind, make_order(), "Bionova Club", "", "https://x.test/admin")
            assert "<script>" not in html and "BPC-157 <b>" not in html
        confirmation = render_html("confirmation", make_order(), "Bionova Club")
        assert "$48.94" in confirmation and "$8.95" in confirmation and "Order received" in confirmation

    def test_free_shipping_is_shown_as_free(self):
        order = make_order()
        order.shipping, order.total = 0, 3999
        assert ">Free<" in render_html("confirmation", order, "Bionova Club")

    def test_tracking_and_admin_link_appear_only_where_they_belong(self):
        assert "1Z999" in render_html("shipped", make_order(), "S")
        assert "1Z999" not in render_html("confirmation", make_order(), "S")
        assert "Open the admin" in render_html("admin", make_order(), "S", "", "https://x.test/admin")
        assert "Open the admin" not in render_html("admin", make_order(), "S", "", "")

    def test_message_has_a_plain_text_and_an_html_part(self, monkeypatch):
        sent = []

        class FakeSmtp:
            def __init__(self, *a, **k): ...
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def ehlo(self): ...
            def has_extn(self, name):
                return False

            def login(self, *a): ...
            def send_message(self, message):
                sent.append(message)

        monkeypatch.setattr(smtp_module.smtplib, "SMTP", FakeSmtp)
        cfg = SmtpSettings(host="smtp.example.com", **{"from": "a@b.test"})
        smtp_module.send_mail(cfg, to="c@d.test", subject="Hi", body="plain text", html="<p>styled</p>")
        parsed = message_from_string(sent[0].as_string())
        assert [p.get_content_type() for p in parsed.walk()][1:] == ["text/plain", "text/html"]
