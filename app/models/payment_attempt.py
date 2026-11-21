from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow


class PaymentAttempt(Base):
    """One charge try for a checkout session: succeeded, declined, or errored. A retry adds a new row."""

    __tablename__ = "payment_attempts"
    __table_args__ = (
        Index("ix_payment_attempts_session", "session_id"),
        Index("ix_payment_attempts_at", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stores.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    outcome: Mapped[str] = mapped_column(String(16))  # succeeded | declined | error
    reason: Mapped[str] = mapped_column(String(200), default="")
    method_id: Mapped[str] = mapped_column(String(40), default="")
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
