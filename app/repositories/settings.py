from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.models import AppSetting


class SettingsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def all(self) -> dict[str, dict]:
        return {row.key: row.value for row in self.db.scalars(select(AppSetting))}

    def set(self, key: str, value: dict) -> None:
        self.db.merge(AppSetting(key=key, value=value))
        self.db.flush()

    def insert_if_missing(self, key: str, value: dict) -> None:
        stmt = mysql_insert(AppSetting).values(key=key, value=value).prefix_with("IGNORE")
        self.db.execute(stmt)
