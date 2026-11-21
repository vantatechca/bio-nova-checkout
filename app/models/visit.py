from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow


class Visit(Base):
    """A checkout page view.

    ``visitor`` is always a salted hash (of either a first-party cookie or IP + user agent), never the IP. ``ip``
    is the IP itself, kept subject to ``VISIT_IP_MODE`` (truncated by default, off, or in full) -- see
    ``app.services.visits.stored_ip``.
    """

    __tablename__ = "visits"
    __table_args__ = (
        Index("ix_visits_at", "at"),
        Index("ix_visits_dedupe", "session_id", "visitor", "at"),
        Index("ix_visits_ip", "ip"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stores.id"), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    session_id: Mapped[str] = mapped_column(String(64))
    visitor: Mapped[str] = mapped_column(String(12))
    device: Mapped[str] = mapped_column(String(10))
    referrer: Mapped[str] = mapped_column(String(100), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    country: Mapped[str] = mapped_column(String(2), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    asn: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    isp: Mapped[str] = mapped_column(String(200), default="")
