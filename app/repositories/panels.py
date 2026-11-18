from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import PanelItem, PanelLog, PanelVersion


class PanelRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- stored sections
    def get(self, panel: str, section: str, *, lock: bool = False) -> PanelItem | None:
        stmt = select(PanelItem).where(PanelItem.panel == panel, PanelItem.section == section)
        return self.db.scalar(stmt.with_for_update() if lock else stmt)

    def list_panel(self, panel: str) -> list[PanelItem]:
        return list(self.db.scalars(select(PanelItem).where(PanelItem.panel == panel)))

    def add(self, item: PanelItem) -> PanelItem:
        self.db.add(item)
        self.db.flush()
        return item

    # ---- versions
    def last_version_number(self, panel: str, section: str) -> int:
        stmt = select(func.max(PanelVersion.version)).where(
            PanelVersion.panel == panel, PanelVersion.section == section
        )
        return self.db.scalar(stmt) or 0

    def add_version(self, version: PanelVersion) -> None:
        self.db.add(version)
        self.db.flush()

    def list_versions(self, panel: str, section: str) -> list[PanelVersion]:
        stmt = (
            select(PanelVersion)
            .where(PanelVersion.panel == panel, PanelVersion.section == section)
            .order_by(PanelVersion.version.desc())
        )
        return list(self.db.scalars(stmt))

    def get_version(self, panel: str, section: str, number: int) -> PanelVersion | None:
        return self.db.scalar(
            select(PanelVersion).where(
                PanelVersion.panel == panel, PanelVersion.section == section, PanelVersion.version == number
            )
        )

    def prune_versions(self, panel: str, section: str, keep_count: int, older_than: datetime) -> int:
        """Drops versions that are both outside the newest ``keep_count`` and older than ``older_than``."""
        beyond_the_newest = (
            select(PanelVersion.id, PanelVersion.created_at)
            .where(PanelVersion.panel == panel, PanelVersion.section == section)
            .order_by(PanelVersion.version.desc())
            .offset(keep_count)
            .limit(1_000_000)  # MySQL needs a LIMIT to accept an OFFSET
        )
        expired = [row.id for row in self.db.execute(beyond_the_newest) if row.created_at < older_than]
        if expired:
            self.db.execute(delete(PanelVersion).where(PanelVersion.id.in_(expired)))
        return len(expired)

    def sections_with_versions(self) -> list[tuple[str, str]]:
        rows = self.db.execute(select(PanelVersion.panel, PanelVersion.section).distinct()).all()
        return [(panel, section) for panel, section in rows]

    def purge_deleted(self, deleted_before: datetime) -> int:
        """Permanently removes sections soft-deleted before the cutoff, together with their versions."""
        rows = self.db.execute(
            select(PanelItem.id, PanelItem.panel, PanelItem.section).where(
                PanelItem.deleted.is_(True), PanelItem.deleted_at < deleted_before
            )
        ).all()
        for item_id, panel, section in rows:
            self.db.execute(delete(PanelVersion).where(PanelVersion.panel == panel, PanelVersion.section == section))
            self.db.execute(delete(PanelItem).where(PanelItem.id == item_id))
        return len(rows)

    # ---- activity log
    def recent_log(self, actor: str, limit: int) -> list[PanelLog]:
        stmt = select(PanelLog).where(PanelLog.actor == actor).order_by(PanelLog.id.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def purge_log(self, older_than: datetime) -> int:
        return self.db.execute(delete(PanelLog).where(PanelLog.created_at < older_than)).rowcount or 0
