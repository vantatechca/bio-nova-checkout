"""Transactional outbox tables.

Rows are written in the same transaction as the order change that caused them and delivered
later by the background worker, so nothing is lost if the process crashes mid-request.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Index, Integer, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow

MediumText = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


class DeliveryState:
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class EmailStatus:
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # SMTP not configured


class EmailLog(Base):
    __tablename__ = "email_log"
    __table_args__ = (
        Index("ix_email_log_created_at", "created_at"),
        Index("ix_email_log_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    type: Mapped[str] = mapped_column(String(20))
    order_number: Mapped[int] = mapped_column(BigInteger)
    to_addr: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(MediumText)
    status: Mapped[str] = mapped_column(String(10), default=EmailStatus.QUEUED)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_created_at", "created_at"),
        Index("ix_webhook_deliveries_state_next_attempt_at", "state", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    event: Mapped[str] = mapped_column(String(40))
    order_number: Mapped[int] = mapped_column(BigInteger)
    url: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(MediumText)  # frozen at enqueue time so retries are byte-identical
    signature: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(10), default=DeliveryState.PENDING)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
