from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbSession, StoreScope
from app.schemas.sessions import AbandonedSessionsOut, TimelineItemOut
from app.services import sessions

router = APIRouter(prefix="/api/admin/sessions", tags=["admin: sessions"])

HoursQuery = Query(default=6, ge=1, le=24 * 30)


@router.get("/abandoned", response_model=AbandonedSessionsOut)
def abandoned(db: DbSession, store: StoreScope, hours: int = HoursQuery):
    rows, _has_more = sessions.abandoned_sessions(db, hours, store)
    return AbandonedSessionsOut(hours=hours, rows=rows)


@router.get("/{session_id}/timeline", response_model=list[TimelineItemOut])
def timeline(session_id: str, db: DbSession):
    return sessions.session_timeline(db, session_id)
