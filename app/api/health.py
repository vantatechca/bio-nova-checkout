from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(db: DbSession) -> dict[str, bool]:
    """Liveness + database connectivity (for load balancers and uptime monitors)."""
    db.execute(text("SELECT 1"))
    return {"ok": True}
