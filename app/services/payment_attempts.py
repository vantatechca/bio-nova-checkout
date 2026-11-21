"""Records payment attempts (succeeded / declined / error), so declines can be reported on."""

from __future__ import annotations

import logging

from app.database import session_scope
from app.models import PaymentAttempt
from app.repositories import PaymentAttemptRepository

log = logging.getLogger(__name__)


def record_outcome(*, store_id: int, session_id: str, outcome: str, reason: str = "", method_id: str = "") -> None:
    """Best effort, on its own connection and transaction: a decline must be recorded even though the request's
    own transaction is about to be rolled back (the order was never created), so a savepoint isn't enough here."""
    try:
        with session_scope() as db:
            repo = PaymentAttemptRepository(db)
            repo.add(
                PaymentAttempt(
                    store_id=store_id,
                    session_id=session_id,
                    outcome=outcome,
                    reason=reason[:200],
                    method_id=method_id[:40],
                    attempt_no=repo.count_for(session_id) + 1,
                )
            )
    except Exception:
        log.exception("Could not record payment attempt")
