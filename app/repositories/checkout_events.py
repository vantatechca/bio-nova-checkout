from __future__ import annotations

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.models import CheckoutEvent
from app.models.types import utcnow


class CheckoutEventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(self, store_id: int, session_id: str, step: str) -> None:
        """At most one row per ``(session_id, step)``; reaching a step again is a no-op, not an error."""
        stmt = mysql_insert(CheckoutEvent).values(store_id=store_id, session_id=session_id, at=utcnow(), step=step)
        self.db.execute(stmt.prefix_with("IGNORE"))
