"""Time-related helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

# Beijing is UTC+8 — most GeoLife data was collected there.
BEIJING_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
UTC_TZ = timezone.utc


def to_local(timestamp: datetime, target_tz=BEIJING_TZ) -> datetime:
    """Coerce a datetime to the given timezone (defaults to Asia/Shanghai).

    If the input is naive we assume it's already in the target zone.
    If it's aware we convert.
    """
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=target_tz)
    return timestamp.astimezone(target_tz)


def gmt_to_local(timestamp: datetime, target_tz=BEIJING_TZ) -> datetime:
    """Treat a (naive) timestamp as UTC then convert to local."""
    return timestamp.replace(tzinfo=UTC_TZ).astimezone(target_tz)


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def in_any_range(hour: int, ranges: Iterable[tuple[int, int]]) -> bool:
    """Return True if ``hour`` falls in any (start, end) range.

    Range is inclusive at the start, exclusive at the end. If ``start > end``
    the range wraps midnight (e.g. ``(22, 6)`` covers 22..23 and 0..5).
    """
    for start, end in ranges:
        if start <= end:
            if start <= hour < end:
                return True
        else:  # wraps midnight
            if hour >= start or hour < end:
                return True
    return False
