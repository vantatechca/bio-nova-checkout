"""Content panels: the shape of what a bot may push, and what the API sends back."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StringConstraints, model_validator


class StrictModel(BaseModel):
    """Unknown fields are rejected, so a typo never silently drops data."""

    model_config = ConfigDict(extra="forbid")


def _number_to_text(value: Any) -> Any:
    return str(value) if isinstance(value, int | float) and not isinstance(value, bool) else value


def _text(max_length: int, min_length: int = 0):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


Label = _text(120, min_length=1)
Short = _text(60)
Line = _text(300)
Note = _text(1000)
# A value shown as text. Numbers are accepted and kept as text, so "12.5" and 12.5 both work.
Cell = Annotated[_text(300), BeforeValidator(_number_to_text)]
Url = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000, pattern=r"^https?://\S+$")]
Last4 = Annotated[str, StringConstraints(pattern=r"^\d{4}$")]
Currency = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z]{3}$", to_upper=True)]


class Metric(StrictModel):
    """A stat tile."""

    label: Label
    value: Cell
    trend: Cell | None = None  # e.g. "+12%"
    hint: Line | None = None


class Entry(StrictModel):
    """One item in a list; may carry a small thumbnail."""

    title: Label
    subtitle: Line | None = None
    city: Short | None = None
    url: Url | None = None
    image_url: Url | None = None
    status: Short | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    value: Cell | None = None
    note: Line | None = None
    updated_at: datetime | None = None


class SiteRow(StrictModel):
    name: Label
    url: Url | None = None
    status: Short | None = None
    uptime_pct: float | None = Field(default=None, ge=0, le=100)
    response_ms: int | None = Field(default=None, ge=0)
    last_checked_at: datetime | None = None


class CardRow(StrictModel):
    """Only the last four digits are ever accepted."""

    label: Label
    last4: Last4
    brand: Short | None = None
    note: Line | None = None
    spend: float | None = Field(default=None, ge=0)
    limit: float | None = Field(default=None, ge=0)
    currency: Currency | None = None
    status: Short | None = None


class Step(StrictModel):
    """One stage in a numbered "how this works" flow, shown as a row of cards linked by arrows."""

    title: Label
    text: Line | None = None


class BarItem(StrictModel):
    """One bar in a simple bar chart."""

    label: Label
    value: Cell
    hint: Line | None = None


class ChecklistItem(StrictModel):
    text: Line
    owner: Short | None = None  # who it's waiting on, shown as a small tag
    done: StrictBool = False


class DataTable(StrictModel):
    columns: list[_text(80, min_length=1)] = Field(min_length=1, max_length=12)
    rows: list[list[Cell]] = Field(max_length=500)

    @model_validator(mode="after")
    def _rows_fit_the_columns(self) -> DataTable:
        for number, row in enumerate(self.rows, start=1):
            if len(row) != len(self.columns):
                raise ValueError(f"row {number} has {len(row)} cells but there are {len(self.columns)} columns")
        return self


class PanelContent(StrictModel):
    """Everything a section can show. All parts are optional and can be combined."""

    headline: Line | None = None
    alert: Line | None = None  # a one-line callout/warning, shown above everything else in the section
    summary: _text(2000) | None = None
    metrics: list[Metric] | None = Field(default=None, max_length=24)
    steps: list[Step] | None = Field(default=None, max_length=12)  # a numbered "how this works" flow
    bars: list[BarItem] | None = Field(default=None, max_length=60)  # a simple bar chart
    bars_style: Literal["rows", "columns"] = (
        "rows"  # "rows": horizontal bars (ranked lists); "columns": vertical (e.g. a day-by-day series)
    )
    bars_total: Cell | None = None  # an optional total line shown under the bar chart
    entries: list[Entry] | None = Field(default=None, max_length=200)
    sites: list[SiteRow] | None = Field(default=None, max_length=200)  # Sites > Live Sites only
    cards: list[CardRow] | None = Field(default=None, max_length=50)  # Ads Data > Credit Card Info only
    table: DataTable | None = None
    checklist: list[ChecklistItem] | None = Field(
        default=None, max_length=50
    )  # a to-do list, each item may name an owner


class WriteIn(StrictModel):
    content: PanelContent
    # Accepted for older callers. It is never used to publish: see ``services.panels.write``.
    visible: StrictBool = False


class VisibleIn(StrictModel):
    visible: StrictBool


class RestoreIn(StrictModel):
    version: int = Field(ge=1)


# ---------------------------------------------------------------- responses
class SectionOut(BaseModel):
    """A section as the API owner sees it: live content, and any draft waiting behind it."""

    id: str
    title: str
    icon: str
    subtitle: str
    tier: str | None
    status: str  # live | hidden | coming_soon
    visible: bool
    content: dict | None
    pending: dict | None
    deleted: bool
    updated_at: datetime | None


class PanelOut(BaseModel):
    panel: str
    title: str
    sections: list[SectionOut]


class WriteOut(SectionOut):
    version: int | None  # the snapshot taken of what was there before; null when the section is new


class DeleteOut(BaseModel):
    deleted: bool
    version: int | None


class VersionOut(BaseModel):
    version: int
    action: str
    created_at: datetime


class VersionDetailOut(VersionOut):
    content: dict


class LogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section: str
    action: str
    outcome: str
    message: str | None
    created_at: datetime


class LogOut(BaseModel):
    entries: list[LogEntryOut]


class DisplaySection(BaseModel):
    """A section as the admin page shows it: live content, or a "coming soon" placeholder."""

    id: str
    title: str
    icon: str
    subtitle: str
    tier: str | None
    status: str  # live | coming_soon
    content: dict | None


class DisplayPanel(BaseModel):
    panel: str
    title: str
    sections: list[DisplaySection]
