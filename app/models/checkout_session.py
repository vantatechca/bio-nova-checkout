from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow


class SessionStatus:
    OPEN = "open"
    COMPLETE = "complete"
    EXPIRED = "expired"


class CheckoutSession(Base):
    """A cart handed over by the store; the customer pays against it exactly once."""

    __tablename__ = "checkout_sessions"
    __table_args__ = (
        Index("ix_checkout_sessions_created_at", "created_at"),
        Index("ix_checkout_sessions_status_expires_at", "status", "expires_at"),
        Index("ix_checkout_sessions_utm_campaign", "utm_campaign"),
        Index("ix_checkout_sessions_internal", "is_internal"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stores.id"), index=True)  # which store sent the cart
    status: Mapped[str] = mapped_column(String(16), default=SessionStatus.OPEN)
    currency: Mapped[str] = mapped_column(String(3))
    items: Mapped[list] = mapped_column(JSON)  # snapshot of the line items sent by the store
    subtotal: Mapped[int] = mapped_column(BigInteger)
    shipping: Mapped[int] = mapped_column(BigInteger)
    tax: Mapped[int] = mapped_column(BigInteger)
    total: Mapped[int] = mapped_column(BigInteger)
    customer_name: Mapped[str] = mapped_column(String(200), default="")
    customer_email: Mapped[str] = mapped_column(String(200), default="")
    customer_phone: Mapped[str] = mapped_column(String(40), default="")
    success_url: Mapped[str] = mapped_column(Text)
    cancel_url: Mapped[str] = mapped_column(Text, default="")
    external_ref: Mapped[str] = mapped_column(String(200), default="")
    utm_source: Mapped[str] = mapped_column(String(100), default="")
    utm_medium: Mapped[str] = mapped_column(String(100), default="")
    utm_campaign: Mapped[str] = mapped_column(String(200), default="")
    utm_content: Mapped[str] = mapped_column(String(200), default="")
    utm_term: Mapped[str] = mapped_column(String(200), default="")
    click_provider: Mapped[str] = mapped_column(String(20), default="")
    click_id: Mapped[str] = mapped_column(String(200), default="")
    # The utm_*/click_provider/click_id columns above are "last touch": apply() overwrites a blank field as new
    # attribution arrives. first_touch is a frozen snapshot (same shape, via AttributionIn.model_dump()) of
    # whatever attribution was present the first time this visit was ever seen -- set once at creation, never
    # updated again, so both can be reported separately (see docs: Deep2K/landing-path tagging).
    first_touch: Mapped[dict] = mapped_column(JSON, default=dict)
    # 200, matching ShopifyCartIn's Text200 cap -- a narrower column here would silently truncate a long id,
    # risking two distinct ids colliding into the same stored (and reported) value.
    deep2k_anonymous_id: Mapped[str] = mapped_column(String(200), default="")
    deep2k_session_id: Mapped[str] = mapped_column(String(200), default="")
    landing_path: Mapped[str] = mapped_column(String(300), default="")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    order_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Flagged at creation time from the shared internal_ip_ranges/internal_user_agent_markers/internal_header_*
    # config (see app.services.visits.is_internal_request) -- a never-viewed internal session is excluded from
    # the "created" count in the shopper funnel, but the row itself is kept, not dropped.
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    viewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)

    @property
    def is_expired(self) -> bool:
        return self.status == SessionStatus.EXPIRED or (
            self.status == SessionStatus.OPEN and self.expires_at <= utcnow()
        )

    @property
    def customer(self) -> dict:
        return {"name": self.customer_name, "email": self.customer_email, "phone": self.customer_phone}
