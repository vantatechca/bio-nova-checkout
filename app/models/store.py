from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow


class Store(Base):
    """A storefront connected to this checkout (e.g. one Shopify shop).

    All of a store's configuration (branding, payment methods, card setup, webhook...) lives in ``settings``
    (see ``StoreSettings``). ``name`` and ``shopify_domain`` mirror values from it so they can be
    looked up and kept unique with ordinary indexes.
    """

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    shopify_domain: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    settings: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
