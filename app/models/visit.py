from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow


class Visit(Base):
    """A checkout page view. Only a salted hash of IP + user agent is stored, never the IP."""

    __tablename__ = "visits"
    __table_args__ = (
        Index("ix_visits_at", "at"),
        Index("ix_visits_dedupe", "session_id", "visitor", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stores.id"), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    session_id: Mapped[str] = mapped_column(String(64))
    visitor: Mapped[str] = mapped_column(String(12))
    device: Mapped[str] = mapped_column(String(10))
    referrer: Mapped[str] = mapped_column(String(100), default="")
