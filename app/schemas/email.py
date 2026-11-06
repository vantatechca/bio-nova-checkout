from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmailLogOut(BaseModel):
    """Email log row without the (potentially long) body."""

    id: str
    at: datetime
    type: str
    order: int
    to: str
    subject: str
    status: str
    error: str | None
    sent_at: datetime | None


class EmailStats(BaseModel):
    sent: int
    failed: int
    skipped: int


class EmailOverviewOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    settings: dict  # camelCase settings with the SMTP password blanked and a ``passSet`` flag
    stats: EmailStats
    log: list[EmailLogOut]


class RetryOut(BaseModel):
    status: str
    error: str | None
