"""Content-panel API, called by the bot that fills the admin's Ads Data and Sites pages.

Every failure of authentication or routing answers with the very same 404 as a path that does not exist:
an unknown panel, a missing or wrong key, an unknown section, a blocked address and a method the route does
not handle (see ``main.py``). Nothing tells a prober which part of the guess was wrong, and nothing is logged
until a request has a valid key and a real section.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.api.deps import DbSession
from app.config import get_settings
from app.errors import AppError, BadRequest
from app.schemas.panels import (
    DeleteOut,
    LogOut,
    PanelOut,
    RestoreIn,
    SectionOut,
    VersionDetailOut,
    VersionOut,
    VisibleIn,
    WriteOut,
)
from app.security import bearer_token, client_ip, constant_time_equals, panel_limiter
from app.services import panel_content, panels
from app.services.panel_catalog import Section, get_panel, get_section

router = APIRouter(prefix="/api/panels", tags=["content panels"])

MAX_BODY_BYTES = 256 * 1024


def _hidden() -> HTTPException:
    """The framework's own 404, byte for byte."""
    return HTTPException(status_code=404, detail="Not Found")


def authorized_panel(request: Request, panel: str) -> str:
    """Resolves ``{panel}`` to a known panel for a caller holding that panel's key. Anything else is a 404."""
    known = get_panel(panel)
    # Throttle first, whatever happens next. Unknown names share one bucket so guesses cannot grow the table.
    panel_limiter.hit(f"{panel if known else '*'}|{client_ip(request)}")
    settings = get_settings()
    expected = getattr(settings, known.key_setting) if known else None
    if not known or not expected:
        raise _hidden()
    allowed = settings.panel_ip_allowlist
    if allowed and client_ip(request) not in allowed:
        raise _hidden()
    if not constant_time_equals(bearer_token(request), expected):
        raise _hidden()
    return panel


Panel = Annotated[str, Depends(authorized_panel)]


@dataclass(frozen=True)
class Target:
    panel: str
    section: Section


def real_section(panel: Panel, section: str) -> Target:
    found = get_section(panel, section)
    if found is None:
        raise _hidden()
    return Target(panel, found)


Section_ = Annotated[Target, Depends(real_section)]


@asynccontextmanager
async def activity(target: Target, action: str) -> AsyncIterator[None]:
    """Logs the call once it is known how it ended (own transaction: see ``panels.record_activity``)."""
    actor, section = target.panel, target.section.id
    try:
        yield
    except AppError as exc:
        await run_in_threadpool(panels.record_activity, actor, actor, section, action, "rejected", exc.message)
        raise
    except Exception as exc:
        await run_in_threadpool(panels.record_activity, actor, actor, section, action, "error", type(exc).__name__)
        raise
    else:
        await run_in_threadpool(panels.record_activity, actor, actor, section, action, "ok")


async def read_json(request: Request) -> object:
    """Read after authentication: a wrong key never gets to see a body-validation error."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise BadRequest("Body too large (256 KB at most)")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise BadRequest("Body too large (256 KB at most)")
    try:
        return json.loads(raw)
    except ValueError:
        raise BadRequest("Body must be valid JSON") from None


# ---------------------------------------------------------------- reads
@router.get("/{panel}", response_model=PanelOut)
def get_panel_overview(panel: Panel, db: DbSession):
    """The catalog plus everything stored, drafts included."""
    return panels.overview(db, panel)


# Registered before /{panel}/{section}, or "log" would be taken for a section name.
@router.get("/{panel}/log", response_model=LogOut)
def get_log(panel: Panel, db: DbSession):
    """This key's own recent activity. Never another panel's."""
    return {"entries": panels.recent_activity(db, panel)}


@router.get("/{panel}/{section}", response_model=SectionOut)
def get_section_view(target: Section_, db: DbSession):
    return panels.read_section(db, target.panel, target.section)


# ---------------------------------------------------------------- writes
@router.put("/{panel}/{section}", response_model=WriteOut)
async def put_section(request: Request, target: Section_, db: DbSession):
    """Push content. It never publishes by itself, whatever the body says; a live section keeps showing as it is
    and the new content waits as a draft until ``PATCH`` publishes it."""
    async with activity(target, "put"):
        body = await read_json(request)
        content = panel_content.validate_write(target.panel, target.section.id, body)
        row, version = await run_in_threadpool(panels.write, db, target.panel, target.section.id, content)
    return {**panels.section_view(target.section, row), "version": version}


@router.patch("/{panel}/{section}", response_model=WriteOut)
async def patch_section(request: Request, target: Section_, db: DbSession):
    """The only call that publishes (``{"visible": true}``) or hides (``{"visible": false}``) a section."""
    async with activity(target, "patch"):
        body = VisibleIn.model_validate(await _object(request))
        row, version = await run_in_threadpool(panels.set_visible, db, target.panel, target.section.id, body.visible)
    return {**panels.section_view(target.section, row), "version": version}


@router.delete("/{panel}/{section}", response_model=DeleteOut)
async def delete_section(target: Section_, db: DbSession):
    async with activity(target, "delete"):
        version = await run_in_threadpool(panels.remove, db, target.panel, target.section.id)
    return {"deleted": True, "version": version}


# ---------------------------------------------------------------- history
@router.get("/{panel}/{section}/versions", response_model=list[VersionOut])
def get_versions(target: Section_, db: DbSession):
    """Metadata only (no content), so it stays cheap."""
    return [
        VersionOut(version=v.version, action=v.action, created_at=v.created_at)
        for v in panels.list_versions(db, target.panel, target.section.id)
    ]


@router.get("/{panel}/{section}/versions/{number}", response_model=VersionDetailOut)
def get_version(target: Section_, number: int, db: DbSession):
    v = panels.get_version(db, target.panel, target.section.id, number)
    return VersionDetailOut(version=v.version, action=v.action, created_at=v.created_at, content=v.payload)


@router.post("/{panel}/{section}/restore", response_model=WriteOut)
async def restore_section(request: Request, target: Section_, db: DbSession):
    """Brings an earlier version back (hidden, as a restore never publishes). The restore can be undone too."""
    async with activity(target, "restore"):
        body = RestoreIn.model_validate(await _object(request))
        row, version = await run_in_threadpool(panels.restore, db, target.panel, target.section.id, body.version)
    return {**panels.section_view(target.section, row), "version": version}


async def _object(request: Request) -> dict:
    body = await read_json(request)
    if not isinstance(body, dict):
        raise BadRequest("Send a JSON object")
    return body
