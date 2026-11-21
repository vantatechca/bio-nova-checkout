from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow

# In the order a customer normally reaches them. The funnel report shows them in this order.
STEPS = ("form_started", "contact_done", "address_done", "method_chosen", "card_entered", "pay_clicked")


class CheckoutEvent(Base):
    """One checkout-form milestone reached, for a funnel deeper than just "viewed" / "ordered".

    At most one row per ``(session_id, step)``: reaching a step twice (e.g. a reload) doesn't count again.
    """

    __tablename__ = "checkout_events"
    __table_args__ = (Index("ix_checkout_events_session_step", "session_id", "step", unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stores.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    step: Mapped[str] = mapped_column(String(20))
