"""Content panels: admin pages made of fixed sections that a bot fills through a private API.

``PanelItem`` is the stored content of one section. ``PanelVersion`` keeps a snapshot taken before every change
(so any change can be undone) and ``PanelLog`` is the append-only activity log, one audience per panel key.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.types import UTCDateTime, utcnow


class PanelItem(Base):
    __tablename__ = "panel_items"
    __table_args__ = (UniqueConstraint("panel", "section", name="uq_panel_items_panel_section"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    panel: Mapped[str] = mapped_column(String(32))
    section: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)  # what is live (or what will be, once published)
    pending_payload: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)  # staged draft
    visible: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class PanelVersion(Base):
    __tablename__ = "panel_versions"
    __table_args__ = (UniqueConstraint("panel", "section", "version", name="uq_panel_versions_panel_section_version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    panel: Mapped[str] = mapped_column(String(32))
    section: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)  # 1, 2, 3... per section, never reused
    action: Mapped[str] = mapped_column(String(16))  # put | patch | delete | restore: what the snapshot preceded
    payload: Mapped[dict] = mapped_column(JSON)  # full content as it was before that action
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PanelLog(Base):
    __tablename__ = "panel_log"
    __table_args__ = (Index("ix_panel_log_actor_created_at", "actor", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(32))  # whose key made the call (the panel it belongs to)
    panel: Mapped[str] = mapped_column(String(32))
    section: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))  # ok | rejected | error
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
