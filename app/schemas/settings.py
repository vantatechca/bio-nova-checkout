"""Runtime-editable business settings. These models are both the API payloads and what is persisted."""

from __future__ import annotations

import ipaddress
import re
import secrets
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import CamelModel, Text40, Text80, Text100, Text200, Text300, Text500, Text1000, Text2000

DEFAULT_BANK = (
    'Send {total} by bank transfer and put "Order #{order}" as the reference. '
    "We mark your order paid as soon as it arrives."
)


def new_secret(prefix: str, nbytes: int = 24) -> str:
    return f"{prefix}_{secrets.token_hex(nbytes)}"


class PaymentMethod(CamelModel):
    id: str = ""
    label: Text80 = ""
    type: Literal["offline", "test", "card"] = "offline"
    instructions: Text300 = ""
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def _clean_id(cls, v: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "", v)[:40]


def default_payment_methods() -> list[PaymentMethod]:
    return [
        PaymentMethod(id="bank", label="Bank transfer", instructions=DEFAULT_BANK),
        PaymentMethod(
            id="test",
            label="Test payment (no real charge)",
            type="test",
            instructions="Marks the order as paid. Replace with a real gateway before going live.",
        ),
    ]


def _check_currency(v: str) -> str:
    v = v.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", v):
        raise ValueError("currency must be a 3-letter code")
    return v


def _check_http_url(v: str) -> str:
    v = v.strip()
    if v and urlparse(v).scheme not in ("http", "https"):
        raise ValueError("must be an http(s) URL")
    return v


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _check_secure_url(v: str) -> str:
    """Payment tokens must only travel over https (plain http is allowed for local development only)."""
    v = v.strip()
    if not v:
        return v
    parts = urlparse(v)
    if not parts.hostname or parts.scheme not in ("http", "https"):
        raise ValueError("must be a full URL such as https://client.example/api/charge")
    if parts.scheme == "http" and parts.hostname not in _LOCAL_HOSTS:
        raise ValueError("must use https")
    return v


_HOSTNAME = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")


def _check_shop_domain(v: str) -> str:
    """Accepts ``my-shop.myshopify.com`` (also tolerates a pasted https:// URL or trailing slash)."""
    v = re.sub(r"^https?://", "", v.strip().lower()).rstrip("/")
    if v and not _HOSTNAME.fullmatch(v):
        raise ValueError("enter the shop's domain, e.g. my-shop.myshopify.com")
    return v


def _check_ip_ranges(v: str) -> str:
    """Comma separated IPs/CIDRs (e.g. "203.0.113.0/24, 2001:db8::/32"), validated so a typo fails loudly at
    save time instead of silently never matching anything."""
    cleaned = []
    for part in v.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ipaddress.ip_network(part, strict=False)
        except ValueError as exc:
            raise ValueError(f"{part!r} is not a valid IP address or CIDR range") from exc
        cleaned.append(part)
    return ", ".join(cleaned)


class PromoPerk(CamelModel):
    """One highlight card shown inside the checkout's promo banner (e.g. "Free gift auto-added")."""

    label: Text80 = Field(min_length=1)
    description: Text200 = ""


class NavLink(CamelModel):
    """A link shown in the checkout page's header menu (e.g. HOME, SHOP, FAQ)."""

    label: Text40 = Field(min_length=1)
    url: Text2000

    @field_validator("url")
    @classmethod
    def _require_http_url(cls, v: str) -> str:
        v = _check_http_url(v)
        if not v:
            raise ValueError("link URL is required")
        return v


class StoreSettings(CamelModel):
    store_name: Text100 = "My Store"
    currency: str = "USD"
    api_key: str = Field(default_factory=lambda: new_secret("sk"))
    # Read-only: a bot or analytics tool can use this (see app.api.analytics) to read reports -- attribution,
    # payment attempts, visits, revenue, abandoned sessions -- without the full access an admin login grants.
    analytics_key: str = Field(default_factory=lambda: new_secret("ak"))
    webhook_url: Text2000 = ""
    webhook_secret: str = Field(default_factory=lambda: new_secret("whsec"))
    allowed_domains: Text1000 = ""  # comma separated hostnames allowed in success/cancel URLs; blank = any
    # Comma separated IPs/CIDRs (shared across stores) treated as internal/non-customer traffic for analytics:
    # flagged on each Visit (Visit.is_internal) and reported as a breakdown, never silently dropped from "all".
    internal_ip_ranges: Text2000 = ""
    # A request also counts as internal when its User-Agent contains any of these (case-insensitive substrings) --
    # for a tester that has no stable IP, e.g. a fixed string their browser/script always sends.
    internal_user_agent_markers: Text1000 = ""
    # ...or when it sends this exact header/value pair (a fixed marker a tester's own tooling adds). Both must be
    # set for the check to apply; either blank disables it.
    internal_header_name: Text100 = ""
    internal_header_value: Text200 = ""
    # Session-replay tagging on the checkout page (shared: this whole service is one domain, so one Clarity
    # project covers every store -- Clarity recommends a separate project per *domain*, not per store). Blank
    # project id/key = that tool is simply not loaded; nothing is sent anywhere. See app.services.tracking.
    clarity_project_id: Text40 = ""
    posthog_project_key: Text100 = ""
    posthog_host: Text200 = ""  # blank = PostHog's own default ingestion host
    # Branding shown on the checkout page so it matches the storefront
    logo_url: Text2000 = ""
    store_url: Text2000 = ""  # where the logo links to
    nav_links: list[NavLink] = Field(default_factory=list, max_length=8)
    notice: Text500 = ""  # shown in the highlighted notice box on the checkout page
    # Shown as a callout in the order summary (e.g. a limited-time promo); blank promo_banner = the whole thing is hidden.
    promo_badge: Text100 = ""  # small pill label above the headline, e.g. "Black Friday - no codes needed"
    promo_banner: Text500 = ""  # the bold headline, e.g. "At least 50% off + free bundle on all orders"
    promo_perks: list[PromoPerk] = Field(default_factory=list, max_length=3)  # up to 3 highlight cards below it
    # Shopify connector (redirect a Shopify cart's "Checkout" button here)
    shopify_domain: Text200 = ""
    shopify_storefront_token: Text200 = ""  # Storefront API access token (read-only product data)
    # Card payments: the card is entered into the processor's own fields (a token comes back; the card number never
    # reaches this server) and the charge is made by the client's API. See docs/client-payment-api.md.
    card_provider: Text40 = ""  # which card-field SDK the checkout page loads ("mock" for testing)
    card_public_key: Text200 = ""  # the processor's *publishable* key for those fields
    card_form_url: Text2000 = (
        ""  # provider "embed": the client-hosted card form shown in an iframe (docs/embedded-card-form.md)
    )
    client_api_url: Text2000 = ""  # the client's charge endpoint
    client_api_secret: str = Field(default_factory=lambda: new_secret("capi"))  # signs our requests to that endpoint
    shipping_flat: int = Field(default=0, ge=0)  # minor units; used when the store doesn't send shipping_amount
    free_shipping_min: int = Field(
        default=0, ge=0
    )  # minor units; orders with a subtotal at or above this ship free (0 = never)
    tax_rate_percent: float = Field(default=0, ge=0, le=100)
    payment_methods: list[PaymentMethod] = Field(default_factory=default_payment_methods, max_length=10)

    _currency = field_validator("currency")(_check_currency)
    _webhook_url = field_validator("webhook_url")(_check_http_url)
    _logo_url = field_validator("logo_url")(_check_http_url)
    _store_url = field_validator("store_url")(_check_http_url)
    _shopify_domain = field_validator("shopify_domain")(_check_shop_domain)
    _client_api_url = field_validator("client_api_url")(_check_secure_url)
    _card_form_url = field_validator("card_form_url")(_check_secure_url)
    _internal_ip_ranges = field_validator("internal_ip_ranges")(_check_ip_ranges)
    _posthog_host = field_validator("posthog_host")(_check_http_url)

    @property
    def allowed_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_domains.split(",") if d.strip()]

    @property
    def internal_ip_range_list(self) -> list[str]:
        return [r.strip() for r in self.internal_ip_ranges.split(",") if r.strip()]

    @property
    def internal_user_agent_marker_list(self) -> list[str]:
        return [m.strip().lower() for m in self.internal_user_agent_markers.split(",") if m.strip()]

    @property
    def card_payments_ready(self) -> bool:
        """Card is offered to customers only once the card fields and the client's API are both configured."""
        if not (self.card_provider and self.client_api_url):
            return False
        return bool(self.card_form_url) if self.card_provider == "embed" else True


class StoreSettingsUpdate(CamelModel):
    """PATCH-style update: only fields that are present are applied."""

    store_name: Text100 | None = None
    currency: str | None = None
    webhook_url: Text2000 | None = None
    allowed_domains: Text1000 | None = None
    internal_ip_ranges: Text2000 | None = None
    internal_user_agent_markers: Text1000 | None = None
    internal_header_name: Text100 | None = None
    internal_header_value: Text200 | None = None
    clarity_project_id: Text40 | None = None
    posthog_project_key: Text100 | None = None
    posthog_host: Text200 | None = None
    logo_url: Text2000 | None = None
    store_url: Text2000 | None = None
    nav_links: list[NavLink] | None = Field(default=None, max_length=8)
    notice: Text500 | None = None
    promo_badge: Text100 | None = None
    promo_banner: Text500 | None = None
    promo_perks: list[PromoPerk] | None = Field(default=None, max_length=3)
    shopify_domain: Text200 | None = None
    shopify_storefront_token: Text200 | None = None
    card_provider: Text40 | None = None
    card_public_key: Text200 | None = None
    card_form_url: Text2000 | None = None
    client_api_url: Text2000 | None = None
    shipping_flat: int | None = Field(default=None, ge=0)
    free_shipping_min: int | None = Field(default=None, ge=0)
    tax_rate_percent: float | None = Field(default=None, ge=0, le=100)
    payment_methods: list[PaymentMethod] | None = Field(default=None, max_length=10)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        return _check_currency(v) if v is not None else None

    @field_validator("webhook_url", "logo_url", "store_url")
    @classmethod
    def _http_urls(cls, v: str | None) -> str | None:
        return _check_http_url(v) if v is not None else None

    @field_validator("internal_ip_ranges")
    @classmethod
    def _ip_ranges(cls, v: str | None) -> str | None:
        return _check_ip_ranges(v) if v is not None else None

    @field_validator("posthog_host")
    @classmethod
    def _posthog_host(cls, v: str | None) -> str | None:
        return _check_http_url(v) if v is not None else None

    @field_validator("shopify_domain")
    @classmethod
    def _shop_domain(cls, v: str | None) -> str | None:
        return _check_shop_domain(v) if v is not None else None

    @field_validator("client_api_url", "card_form_url")
    @classmethod
    def _secure_url(cls, v: str | None) -> str | None:
        return _check_secure_url(v) if v is not None else None


class StoreSettingsOut(StoreSettings):
    store_id: int
    public_url: str
    webhook_log: list[dict]


# ---------------------------------------------------------------- email settings
class SmtpSettings(CamelModel):
    host: Text200 = ""
    port: int = Field(default=587, ge=1, le=65535)
    secure: bool = False  # implicit TLS (port 465); otherwise STARTTLS is used when offered
    user: Text200 = ""
    password: str = Field(default="", alias="pass", max_length=500)
    from_address: Text200 = Field(default="", alias="from")

    model_config = ConfigDict(populate_by_name=True)

    @property
    def configured(self) -> bool:
        return bool(self.host and self.from_address)


class NotifyFlags(CamelModel):
    confirmation: bool = True
    paid: bool = True
    shipped: bool = True
    cancelled: bool = True
    admin: bool = True


class EmailSettings(CamelModel):
    admin_email: Text200 = ""  # receives a "new order" alert when set
    notify: NotifyFlags = Field(default_factory=NotifyFlags)
    smtp: SmtpSettings = Field(default_factory=SmtpSettings)


class SmtpUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    host: Text200 | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    secure: bool | None = None
    user: Text200 | None = None
    password: str | None = Field(default=None, alias="pass", max_length=500)  # blank keeps the saved password
    clear_pass: bool = Field(default=False, alias="clearPass")
    from_address: Text200 | None = Field(default=None, alias="from")


class NotifyUpdate(BaseModel):
    confirmation: bool | None = None
    paid: bool | None = None
    shipped: bool | None = None
    cancelled: bool | None = None
    admin: bool | None = None


class EmailSettingsUpdate(CamelModel):
    admin_email: Text200 | None = None
    notify: NotifyUpdate | None = None
    smtp: SmtpUpdate | None = None

    @field_validator("admin_email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        if v and not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", v):
            raise ValueError("Admin email is not a valid address")
        return v


class EmailTestIn(BaseModel):
    to: str

    @field_validator("to")
    @classmethod
    def _valid(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", v):
            raise ValueError("Enter a valid recipient address")
        return v


# Which store settings belong to one store and which are shared by every store on this checkout.
STORE_ONLY_FIELDS = frozenset(
    {
        "store_name",
        "logo_url",
        "store_url",
        "nav_links",
        "notice",
        "shopify_domain",
        "shopify_storefront_token",
    }
)
SHARED_FIELDS = frozenset(StoreSettings.model_fields) - STORE_ONLY_FIELDS
