"""Giờ địa phương theo vị trí cho GeoLife.

File ``.plt`` lưu giờ **GMT** dù người dùng ở đâu. Múi giờ của mỗi điểm được tra
từ toạ độ (``timezonefinder``: offline, đa giác ranh giới múi giờ IANA) rồi đổi
bằng ``zoneinfo`` (có giờ mùa hè). Không dùng UTC+8 cố định: 2.61% số điểm (16
user) ở múi giờ khác, và UTC+8 đặt 21.5% giờ hoạt động của họ vào 1–5 h sáng so
với 7.4% khi tính theo vị trí (mốc 5.7%). Không suy từ kinh độ: Trung Quốc trải
qua khoảng 5 múi giờ địa lý nhưng chỉ dùng 1 giờ chính thức.
Kiểm chứng: notebooks/09_timezone_by_location.ipynb.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import cache, lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from timezonefinder import TimezoneFinder

# Tra múi giờ theo ô lưới 0.01° (~1 km): mỗi ô chỉ tra 1 lần.
TZ_GRID_DECIMALS = 2


@lru_cache(maxsize=1)
def _finder() -> TimezoneFinder:
    return TimezoneFinder()


@cache
def _timezone_of_cell(lat: float, lon: float) -> str:
    return _finder().timezone_at(lat=lat, lng=lon) or "Etc/UTC"


def timezone_names(lat, lon) -> np.ndarray:
    """Tên múi giờ IANA (vd. ``Asia/Shanghai``) cho từng cặp toạ độ."""
    lat = np.round(np.asarray(lat, dtype=float), TZ_GRID_DECIMALS)
    lon = np.round(np.asarray(lon, dtype=float), TZ_GRID_DECIMALS)
    return np.array([_timezone_of_cell(a, b) for a, b in zip(lat, lon, strict=False)], dtype=object)


def local_times(times, lat, lon) -> list[datetime]:
    """Giờ địa phương (naive) của từng thời điểm GMT naive, theo múi giờ của toạ độ
    tương ứng - cùng quy tắc với ``localize_by_location`` nhưng cho danh sách
    ``datetime`` (classifier), không cần DataFrame."""
    return [t.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(name)).replace(tzinfo=None)
            for t, name in zip(times, timezone_names(lat, lon), strict=True)]


def localize_by_location(
    df: pd.DataFrame,
    column: str = "datetime",
    output_column: str = "timestamp_local",
    tz_column: str = "tz_name",
) -> pd.DataFrame:
    """Thêm ``tz_column`` (múi giờ của toạ độ) và ``output_column`` (giờ địa
    phương, dạng naive vì 1 cột pandas chỉ giữ được 1 múi giờ).

    ``column`` là giờ GMT naive và được giữ nguyên để kiểm tra lại. Cần cột
    ``lat``, ``lon``. Trả về bản sao; input không bị sửa.
    """
    if df is None or df.empty or column not in df.columns:
        return df

    out = df.copy()
    out[tz_column] = timezone_names(out["lat"], out["lon"])
    utc = pd.to_datetime(out[column]).dt.tz_localize("UTC")
    local = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
    for name, idx in out.groupby(tz_column).groups.items():
        local.loc[idx] = utc.loc[idx].dt.tz_convert(name).dt.tz_localize(None)
    out[output_column] = local
    return out
