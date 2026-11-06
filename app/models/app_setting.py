from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppSetting(Base):
    """Key/value store for runtime-editable configuration (``store``, ``email``, ``salt``, ``secret``)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column("k", String(64), primary_key=True)
    value: Mapped[dict] = mapped_column("v", JSON)
