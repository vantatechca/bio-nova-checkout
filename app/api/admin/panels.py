from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbSession
from app.errors import NotFound
from app.schemas.panels import DisplayPanel
from app.services import panels
from app.services.panel_catalog import get_panel

router = APIRouter(prefix="/api/admin/panels", tags=["admin: content panels"])


@router.get("/{panel}", response_model=DisplayPanel)
def show_panel(panel: str, db: DbSession):
    """What the Ads Data / Sites tab shows. The content is shared by every store, so there is no store filter."""
    if get_panel(panel) is None:
        raise NotFound("Panel not found")
    return panels.list_for_display(db, panel)
