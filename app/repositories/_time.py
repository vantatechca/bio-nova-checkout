"""Shared SQL helper for repositories that bucket rows by the caller's local calendar day.

Used identically by VisitRepository.daily()/arrivals() and AttributionRepository.sessions_vs_arrivals() --
factored out so a future change to the bucketing formula (a dialect fix, a different rounding rule) can't be
applied to one copy and missed in the others, silently producing inconsistent day boundaries between reports.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, literal_column


def local_day(column: ColumnElement, tz_offset_minutes: int) -> ColumnElement:
    """The caller's local calendar day for ``column`` (a UTC datetime), per JS ``Date.getTimezoneOffset()``."""
    return func.date(func.date_sub(column, literal_column(f"INTERVAL {int(tz_offset_minutes)} MINUTE")))
