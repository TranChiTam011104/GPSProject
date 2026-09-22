"""Timezone handling for GeoLife (Check Point 1 / Tuần 1).

GeoLife ``.plt`` files store timestamps in **GMT**, regardless of where the
user actually was. Most data was collected in Beijing (UTC+8), so the default
target zone is ``Asia/Shanghai``. Callers can override via the constructor
or :func:`detect_timezone_from_location`.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd


# Beijing is the canonical target — adjust if your subset is from another region.
DEFAULT_TARGET_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


# ── Helpers ────────────────────────────────────────────────────────────────


def detect_timezone_from_location(lat: float, lng: float) -> str:
    """Naive location→timezone heuristic.

    Returns ``"Asia/Shanghai"`` for anything in the rough Beijing box
    (lat 39..41, lng 116..117). Default to the same zone for unknown
    regions because the source dataset is dominated by Beijing traces.
    """
    if 38 <= lat <= 42 and 115 <= lng <= 118:
        return "Asia/Shanghai"
    return "Asia/Shanghai"


def get_timezone_offset(timezone_name: str) -> timedelta:
    """Return the UTC offset for ``timezone_name``.

    GeoLife offsets are fixed (no DST) so we rely on the dataset's known
    regions. Extend this mapping as you onboard new regions.
    """
    mapping = {
        "Asia/Shanghai": timedelta(hours=8),
        "Europe/London": timedelta(hours=0),
        "America/Los_Angeles": timedelta(hours=-8),
    }
    return mapping.get(timezone_name, DEFAULT_TARGET_TZ.utcoffset(None) or timedelta(hours=8))


def localize_dataframe_column(
    df: pd.DataFrame,
    column: str = "timestamp",
    output_column: str = "timestamp_local",
) -> pd.DataFrame:
    """Add a tz-aware local column to ``df`` for downstream consumers.

    Treats the naive values in ``column`` as GMT, converts to ``Asia/Shanghai``
    (UTC+8), and stores the result in ``output_column``. The original column
    is **kept intact** so audit / re-processing stays possible.

    Idempotent: if ``column`` is already tz-aware (e.g. re-running the
    pipeline on previously processed parquet), no localisation is attempted
    — the values are copied straight to ``output_column``.

    Args:
        df:            Input DataFrame (not mutated; a copy is returned).
        column:        Name of the naive GMT column (default ``"timestamp"``).
        output_column: Name of the tz-aware column to add
                       (default ``"timestamp_local"``).

    Returns:
        A copy of ``df`` with ``output_column`` populated.
    """
    if df is None or df.empty or column not in df.columns:
        return df

    out = df.copy()
    # Already tz-aware → copy as-is (e.g. re-running on prior parquet).
    # Note: ``pd.api.types.is_datetime64tz_dtype`` is deprecated under pandas 4.x
    # in favour of ``isinstance(dtype, pd.DatetimeTZDtype)``.
    if isinstance(out[column].dtype, pd.DatetimeTZDtype):
        out[output_column] = out[column]
        return out

    raw = pd.to_datetime(out[column], errors="coerce")
    out[output_column] = (
        raw.dt.tz_localize(timezone.utc, nonexistent="shift_forward", ambiguous="NaT")
            .dt.tz_convert(DEFAULT_TARGET_TZ)
    )
    return out
