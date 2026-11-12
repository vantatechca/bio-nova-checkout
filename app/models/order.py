from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow


class OrderStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    ALL = (PENDING, PROCESSING, SHIPPED, COMPLETED, CANCELLED, REFUNDED)


class PaymentStatus:
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    ALL = (PENDING, PAID, FAILED, REFUNDED)


class Order(Base):
    """A placed order. ``number`` is the customer-facing, auto-incrementing order number."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_status", "status"),
        Index("ix_orders_payment_status", "payment_status"),
        Index("ix_orders_external_ref", "external_ref"),
        Index("ix_orders_paid_at", "paid_at"),
        Index("ix_orders_created_at", "created_at"),
        {"mysql_auto_increment": "1001"},
    )

    number: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stores.id"), index=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True)  # one order per checkout session
    external_ref: Mapped[str] = mapped_column(String(200), default="")

    status: Mapped[str] = mapped_column(String(16), default=OrderStatus.PENDING)
    payment_status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.PENDING)
    payment_method_id: Mapped[str] = mapped_column(String(40))
    payment_method_label: Mapped[str] = mapped_column(String(80))
    payment_instructions: Mapped[str] = mapped_column(Text, default="")
    payment_reference: Mapped[str] = mapped_column(String(200), default="")

    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[int] = mapped_column(BigInteger)
    shipping: Mapped[int] = mapped_column(BigInteger)
    tax: Mapped[int] = mapped_column(BigInteger)
    total: Mapped[int] = mapped_column(BigInteger)

    customer_name: Mapped[str] = mapped_column(String(200))
    customer_email: Mapped[str] = mapped_column(String(200))
    customer_phone: Mapped[str] = mapped_column(String(40), default="")

    ship_line1: Mapped[str] = mapped_column(String(200))
    ship_line2: Mapped[str] = mapped_column(String(200), default="")
    ship_city: Mapped[str] = mapped_column(String(100))
    ship_state: Mapped[str] = mapped_column(String(100), default="")
    ship_postal_code: Mapped[str] = mapped_column(String(20))
    ship_country: Mapped[str] = mapped_column(String(100))

    tracking_number: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.position", lazy="selectin"
    )
    history: Mapped[list[OrderEvent]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderEvent.id", lazy="selectin"
    )

    def add_event(self, text: str, at: datetime | None = None) -> None:
        self.history.append(OrderEvent(text=text, at=at or utcnow()))

    # ---- read-only views consumed by the API schemas
    @property
    def id(self) -> str:
        return self.public_id

    @property
    def customer(self) -> dict:
        return {"name": self.customer_name, "email": self.customer_email, "phone": self.customer_phone}

    @property
    def shipping_address(self) -> dict:
        return {
            "line1": self.ship_line1,
            "line2": self.ship_line2,
            "city": self.ship_city,
            "state": self.ship_state,
            "postal_code": self.ship_postal_code,
            "country": self.ship_country,
        }

    @property
    def payment_method(self) -> dict:
        return {"id": self.payment_method_id, "label": self.payment_method_label}


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_number: Mapped[int] = mapped_column(ForeignKey("orders.number", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(String(300), default="")
    image: Mapped[str] = mapped_column(Text, default="")
    unit_amount: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")


class OrderEvent(Base):
    """One line of the order's audit trail, shown as "History" in the admin."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_number: Mapped[int] = mapped_column(ForeignKey("orders.number", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    text: Mapped[str] = mapped_column(String(500))

    order: Mapped[Order] = relationship(back_populates="history")
