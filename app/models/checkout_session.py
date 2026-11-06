from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Index, String, Text
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
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
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
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    order_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
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
