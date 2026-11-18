"""HTML versions of the order emails, styled like the checkout page.

Email clients ignore stylesheets and most modern CSS, so this is table-based markup with inline styles.
Every value that comes from a customer or a store is escaped.
"""

from __future__ import annotations

from html import escape

from app.models import Order, PaymentStatus
from app.services.money import format_money

BRAND = "#0a47d6"
OK = "#0f8a4f"
INK = "#0e1124"
MUTED = "#6b7280"
LINE = "#e5e7eb"
FONT = "Inter,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"

# (badge text, badge colour, headline, intro) per email type; {name} is the customer's first name.
COPY = {
    "confirmation": ("Order received", BRAND, "Thanks for your order, {name}", "We've got your order #{number}."),
    "paid": (
        "Payment received",
        OK,
        "Payment received, {name}",
        "Your payment has been received and your order is being processed.",
    ),
    "shipped": ("On its way", OK, "Your order has shipped, {name}", "Good news: your order #{number} is on its way."),
    "cancelled": ("Cancelled", "#b42318", "Your order was cancelled", "Your order #{number} has been cancelled."),
    "admin": ("New order", BRAND, "New order #{number}", "A customer just placed an order."),
}


def _e(value: object) -> str:
    return escape(str(value or ""), quote=True)


def _https(url: str) -> str:
    return url.strip() if url and url.strip().lower().startswith(("https://", "http://")) else ""


def _item_row(order: Order, item) -> str:
    image = _https(item.image)
    thumb = (
        f'<img src="{_e(image)}" width="56" height="56" alt="" '
        f'style="display:block;width:56px;height:56px;border-radius:8px;border:1px solid {LINE};object-fit:cover">'
        if image
        else f'<div style="width:56px;height:56px;border-radius:8px;background:#eef3ff;border:1px solid {LINE}"></div>'
    )
    detail = (
        f'<div style="font-size:12px;color:{MUTED};margin-top:2px">{_e(item.description)}</div>'
        if item.description
        else ""
    )
    return f"""
      <tr>
        <td style="padding:14px 0 14px 24px;width:56px;border-top:1px solid {LINE}" valign="middle">{thumb}</td>
        <td style="padding:14px 12px;border-top:1px solid {LINE}" valign="middle">
          <div style="font-size:14.5px;font-weight:700;color:{INK}">{_e(item.name)}</div>{detail}
          <div style="font-size:12px;color:{MUTED};margin-top:2px">Qty {item.quantity}</div>
        </td>
        <td style="padding:14px 24px 14px 0;border-top:1px solid {LINE};text-align:right;white-space:nowrap;font-size:14.5px;font-weight:700;color:{INK}" valign="middle">
          {_e(format_money(item.unit_amount * item.quantity, order.currency))}
        </td>
      </tr>"""


def _line(label: str, value: str, color: str = "#4b5563", bold: bool = False) -> str:
    weight = "700" if bold else "400"
    return (
        f'<tr><td style="padding:4px 0;font-size:14px;color:#4b5563">{label}</td>'
        f'<td style="padding:4px 0;font-size:14px;color:{color};font-weight:{weight};text-align:right">{value}</td></tr>'
    )


def _summary(order: Order) -> str:
    money = lambda n: _e(format_money(n, order.currency))  # noqa: E731
    shipping = f'<span style="color:{OK};font-weight:700">Free</span>' if not order.shipping else money(order.shipping)
    tax = _line("Tax", money(order.tax)) if order.tax else ""
    rows = "".join(_item_row(order, i) for i in order.items)
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LINE};border-radius:12px;border-collapse:separate;overflow:hidden;margin-top:24px">
      <tr><td colspan="3" style="padding:16px 24px">
        <span style="font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:{INK}">Order summary</span>
        <span style="float:right;font-size:13px;color:{MUTED}">Order #{order.number}</span>
      </td></tr>{rows}
      <tr><td colspan="3" style="background:#f6f7f9;border-top:1px solid {LINE};padding:16px 24px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          {_line("Subtotal", money(order.subtotal))}
          {_line("Shipping", shipping)}
          {tax}
          <tr><td style="padding:12px 0 0;border-top:1px solid #d1d5db;font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:{INK}">Total</td>
              <td style="padding:12px 0 0;border-top:1px solid #d1d5db;text-align:right;font-size:26px;font-weight:900;color:{BRAND}">
                <span style="font-size:12px;font-weight:700;color:{MUTED};letter-spacing:.06em">{_e(order.currency)}</span> {money(order.total)}</td></tr>
        </table>
      </td></tr>
    </table>"""


def _box(title: str, body: str, color: str = BRAND, background: str = "#eef3ff") -> str:
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px">
      <tr><td style="background:{background};border-left:4px solid {color};border-radius:8px;padding:14px 16px">
        <div style="font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:{color}">{_e(title)}</div>
        <div style="font-size:14px;color:{INK};margin-top:4px;line-height:1.5">{body}</div>
      </td></tr>
    </table>"""


def _address(order: Order) -> str:
    a = order.shipping_address
    lines = [a["line1"], a["line2"], " ".join(p for p in (a["city"], a["state"], a["postal_code"]) if p), a["country"]]
    return "<br>".join(_e(line) for line in lines if line)


def render_html(email_type: str, order: Order, store_name: str, logo_url: str = "", admin_url: str = "") -> str:
    badge, color, headline, intro = COPY[email_type]
    first = (order.customer_name or "").split(" ")[0] or "there"
    headline = headline.format(name=_e(first), number=order.number)
    intro = intro.format(name=_e(first), number=order.number)

    logo = _https(logo_url)
    brand = (
        f'<img src="{_e(logo)}" alt="{_e(store_name)}" height="44" style="display:inline-block;height:44px;max-width:240px;border:0">'
        if logo
        else f'<span style="font-size:22px;font-weight:900;color:{INK};letter-spacing:.02em">{_e(store_name)}</span>'
    )

    extra = ""
    if email_type == "confirmation" and order.payment_status != PaymentStatus.PAID:
        how = order.payment_instructions or order.payment_method_label
        extra = _box("Payment", _e(how).replace("\n", "<br>"))
    elif email_type == "shipped" and order.tracking_number:
        extra = _box(
            "Tracking number",
            f'<span style="font-size:16px;font-weight:700">{_e(order.tracking_number)}</span>',
            OK,
            "#e6f5ec",
        )
    elif email_type == "cancelled":
        extra = _box(
            "Need help?",
            "If you didn't expect this or you already paid, just reply to this email.",
            "#b42318",
            "#fef3f2",
        )
    elif email_type == "admin":
        who = f"{_e(order.customer_name)} &lt;{_e(order.customer_email)}&gt;"
        extra = _box("Customer", f"{who}<br>{_e(order.payment_method_label)} · {_e(order.payment_status)}")

    summary = "" if email_type == "cancelled" else _summary(order)
    ship_to = (
        ""
        if email_type in ("cancelled", "paid")
        else f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px">
      <tr><td style="font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};padding-bottom:6px">Shipping to</td></tr>
      <tr><td style="font-size:14px;color:{INK};line-height:1.55">{_address(order)}</td></tr>
    </table>"""
    )
    button = (
        f"""
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:24px"><tr>
      <td style="background:{BRAND};border-radius:10px"><a href="{_e(admin_url)}" style="display:inline-block;padding:13px 26px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none">Open the admin</a></td>
    </tr></table>"""
        if email_type == "admin" and _https(admin_url)
        else ""
    )
    footer = (
        "Sent by your checkout."
        if email_type == "admin"
        else f"Questions about your order? Use the chat on our store.<br>{_e(store_name)}"
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{_e(store_name)}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:{FONT}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6"><tr><td align="center" style="padding:24px 12px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border:1px solid {LINE};border-radius:14px;border-collapse:separate;overflow:hidden">
    <tr><td align="center" style="padding:22px 24px;border-bottom:1px solid {LINE}">{brand}</td></tr>
    <tr><td style="padding:28px 24px 8px">
      <span style="display:inline-block;background:{color};color:#ffffff;font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;border-radius:999px;padding:5px 12px">{_e(badge)}</span>
      <h1 style="margin:14px 0 6px;font-size:24px;line-height:1.25;font-weight:800;color:{INK}">{headline}</h1>
      <p style="margin:0;font-size:15px;line-height:1.55;color:#4b5563">{intro}</p>
      {extra}{summary}{ship_to}{button}
    </td></tr>
    <tr><td style="padding:24px;font-size:12.5px;line-height:1.6;color:{MUTED};text-align:center">{footer}</td></tr>
  </table>
</td></tr></table>
</body></html>"""
