"""Content panels: stored sections with version history, undo, soft delete and a safe-publish rule.

The rule that matters most: a routine write never publishes anything, and never takes anything live down.
New content is created hidden; changes to a live section wait as a draft (``pending_payload``) until a separate,
explicit publish promotes them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import session_scope
from app.errors import NotFound
from app.models import PanelItem, PanelLog, PanelVersion
from app.models.types import utcnow
from app.repositories import PanelRepository
from app.services.panel_catalog import PANELS, Section

log = logging.getLogger(__name__)

KEEP_VERSIONS = 30  # newest versions always kept ...
KEEP_DAYS = 90  # ... and anything younger than this, whichever keeps more
RECOVERY_DAYS = 30  # how long a deleted section can still be restored
LOG_DAYS = 180
LOG_PAGE = 100


# ---------------------------------------------------------------- versions
def _snapshot(repo: PanelRepository, row: PanelItem | None, action: str) -> int | None:
    """Saves what the section looks like now. Called before every change, in the same transaction."""
    if row is None:
        return None  # brand new: nothing to preserve yet
    number = repo.last_version_number(row.panel, row.section) + 1
    repo.add_version(
        PanelVersion(panel=row.panel, section=row.section, version=number, action=action, payload=row.payload)
    )
    return number


def _prune(
    repo: PanelRepository, panel: str, section: str, keep_count: int = KEEP_VERSIONS, keep_days: int = KEEP_DAYS
) -> None:
    repo.prune_versions(panel, section, keep_count, utcnow() - timedelta(days=keep_days))


# ---------------------------------------------------------------- writes
def write(db: Session, panel: str, section: str, content: dict) -> tuple[PanelItem, int | None]:
    """Stores pushed content. Never publishes, and never changes what is live."""
    repo = PanelRepository(db)
    row = repo.get(panel, section, lock=True)
    version = _snapshot(repo, row, "put")
    if row is None:
        # Brand new: created hidden, whatever the caller said.
        row = repo.add(PanelItem(panel=panel, section=section, payload=content, visible=False))
    elif row.visible and not row.deleted:
        # Already live: leave what is showing alone and stage the new content as a draft.
        row.pending_payload = content
    else:
        # Not live (hidden or deleted): nothing public is at risk, so apply it directly.
        row.payload = content
        row.pending_payload = None
        row.deleted = False
        row.deleted_at = None
        row.visible = False
    db.flush()
    _prune(repo, panel, section)
    return row, version


def set_visible(db: Session, panel: str, section: str, visible: bool) -> tuple[PanelItem, int | None]:
    """The only thing that publishes (or hides). Publishing promotes a waiting draft."""
    repo = PanelRepository(db)
    row = repo.get(panel, section, lock=True)
    if row is None or row.deleted:
        raise NotFound("Nothing has been stored for this section yet")
    version = _snapshot(repo, row, "patch")
    if visible and row.pending_payload is not None:
        row.payload = row.pending_payload
        row.pending_payload = None
    row.visible = visible  # hiding leaves a waiting draft where it is
    db.flush()
    _prune(repo, panel, section)
    return row, version


def remove(db: Session, panel: str, section: str) -> int | None:
    """Soft delete: hidden at once, restorable for ``RECOVERY_DAYS``. Discards any waiting draft."""
    repo = PanelRepository(db)
    row = repo.get(panel, section, lock=True)
    if row is None or row.deleted:
        raise NotFound("Nothing to delete in this section")
    version = _snapshot(repo, row, "delete")
    row.deleted = True
    row.deleted_at = utcnow()
    row.visible = False  # so a later push can never bring it back live by itself
    row.pending_payload = None
    db.flush()
    _prune(repo, panel, section)
    return version


def restore(db: Session, panel: str, section: str, number: int) -> tuple[PanelItem, int | None]:
    """Puts an earlier version back. Restoring is itself undoable, and the content comes back hidden."""
    repo = PanelRepository(db)
    target = repo.get_version(panel, section, number)
    row = repo.get(panel, section, lock=True)
    if target is None or row is None:
        raise NotFound("That version does not exist")
    version = _snapshot(repo, row, "restore")
    row.payload = target.payload
    row.pending_payload = None
    row.deleted = False
    row.deleted_at = None
    row.visible = False  # never publishes by itself
    db.flush()
    _prune(repo, panel, section)
    return row, version


# ---------------------------------------------------------------- reads
def _view(section: Section, row: PanelItem | None) -> dict:
    stored = row is not None and not row.deleted
    return {
        "id": section.id,
        "title": section.title,
        "icon": section.icon,
        "subtitle": section.subtitle,
        "tier": section.tier,
        "status": "coming_soon" if not stored else ("live" if row.visible else "hidden"),
        "visible": bool(stored and row.visible),
        "content": row.payload if stored else None,
        "pending": row.pending_payload if stored else None,
        "deleted": bool(row is not None and row.deleted),
        "updated_at": row.updated_at if row is not None else None,
    }


def section_view(section: Section, row: PanelItem | None) -> dict:
    return _view(section, row)


def read_section(db: Session, panel: str, section: Section) -> dict:
    return _view(section, PanelRepository(db).get(panel, section.id))


def overview(db: Session, panel: str) -> dict:
    """Every catalog section with whatever is stored for it, hidden or not (the API owner's own view)."""
    stored = {row.section: row for row in PanelRepository(db).list_panel(panel)}
    definition = PANELS[panel]
    return {
        "panel": panel,
        "title": definition.title,
        "sections": [_view(s, stored.get(s.id)) for s in definition.sections],
    }


def list_for_display(db: Session, panel: str) -> dict:
    """What the admin page shows: live content where there is some, a "coming soon" placeholder elsewhere."""
    stored = {row.section: row for row in PanelRepository(db).list_panel(panel) if not row.deleted}
    definition = PANELS[panel]
    sections = []
    for s in definition.sections:
        row = stored.get(s.id)
        live = row is not None and row.visible
        sections.append(
            {
                "id": s.id,
                "title": s.title,
                "icon": s.icon,
                "subtitle": s.subtitle,
                "tier": s.tier,
                "status": "live" if live else "coming_soon",
                "content": row.payload if live else None,
            }
        )
    return {"panel": panel, "title": definition.title, "sections": sections}


def list_versions(db: Session, panel: str, section: str) -> list[PanelVersion]:
    return PanelRepository(db).list_versions(panel, section)


def get_version(db: Session, panel: str, section: str, number: int) -> PanelVersion:
    version = PanelRepository(db).get_version(panel, section, number)
    if version is None:
        raise NotFound("That version does not exist")
    return version


def recent_activity(db: Session, actor: str) -> list[PanelLog]:
    return PanelRepository(db).recent_log(actor, LOG_PAGE)


# ---------------------------------------------------------------- activity log
def record_activity(
    actor: str, panel: str, section: str, action: str, outcome: str, message: str | None = None
) -> None:
    """Writes one log row in its own transaction, so it survives the request's own rollback.

    The log is a record of what was asked, not something that should vanish because the ask failed halfway.
    Logging must never break the request, so a failure here is only reported.
    """
    try:
        with session_scope() as db:
            db.add(
                PanelLog(
                    actor=actor,
                    panel=panel,
                    section=section,
                    action=action,
                    outcome=outcome,
                    message=(message or None) and message[:500],
                )
            )
    except Exception:
        log.exception("Could not write the content-panel activity log")


# ---------------------------------------------------------------- housekeeping
def purge_expired(db: Session, now: datetime | None = None) -> None:
    """Hourly: removes sections deleted longer ago than the recovery window, versions past retention, old log rows."""
    now = now or utcnow()
    repo = PanelRepository(db)
    removed = repo.purge_deleted(now - timedelta(days=RECOVERY_DAYS))
    for panel, section in repo.sections_with_versions():
        _prune(repo, panel, section)
    repo.purge_log(now - timedelta(days=LOG_DAYS))
    if removed:
        log.info("Permanently removed %d deleted panel sections", removed)
