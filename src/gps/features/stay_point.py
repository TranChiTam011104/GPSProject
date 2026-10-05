"""Stay-point detection (Checkpoint 1 / Tuần 1).

Algorithm — sliding-window over a sorted GPS trajectory:

1. Walk the trajectory by index ``i`` (anchor or centroid).
2. Keep expanding the right end of the window while
   - every point in the window is within ``distance_threshold`` of the reference point.
3. If the window covers at least ``time_threshold`` → emit one stay-point
   anchored at the centroid of the window.
4. Resume scanning from the first point *outside* the window.

A window never spans a gap of more than ``max_gap_hours`` between two consecutive
points: the trajectory is cut there first (see ``MAX_GAP_HOURS``).

Supports two distance modes:
- "anchor": All points must be within distance_threshold of the ANCHOR (first point).
  Standard Li et al. 2008 algorithm.
- "centroid": All points must be within distance_threshold of the RUNNING CENTROID.
  Centroid is recalculated after each point is added to the window.
  More flexible for users who move around within a stay region.

Returns a list of :class:`StayPoint`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import asin, cos, radians, sin, sqrt

import numpy as np
import pandas as pd

from gps.utils.geo import EARTH_RADIUS_KM, haversine_meters

# Cắt quỹ đạo tại mọi khoảng ngắt > 18 h giữa 2 điểm liên tiếp; khoảng ngắt ngắn
# hơn (kể cả giữa 2 file .plt) được nối qua. 18 h là mốc giờ đầu tiên mà tỉ lệ
# "lần ghi sau bắt đầu trong vòng 200 m" chạm mức nền của khoảng ngắt > 24 h
# (19.7% ± 1.5%), tức không còn khác thói quen quay lại chỗ quen. Số đêm có
# stay-point tăng 395 -> 3,340 (notebooks/04_file_boundaries.ipynb).
MAX_GAP_HOURS = 18.0


class DistanceMode(str, Enum):
    """Distance calculation mode for stay-point detection."""

    #: Standard Li et al. 2008: all points compared to anchor (first point in window)
    ANCHOR = "anchor"
    #: Running centroid: all points compared to the running mean of window
    CENTROID = "centroid"


def _mean_altitude(alts: list) -> float:
    """Trung bình các độ cao hợp lệ trong cửa sổ (bỏ None / NaN); NaN nếu không có
    giá trị nào - không dùng 0.0, vì 0 m là một độ cao có thật."""
    valid = [a for a in alts if a is not None and a == a]
    return float(sum(valid) / len(valid)) if valid else float("nan")


# ── Output value objects ─────────────────────────────────────────────────────


@dataclass
class StayPoint:
    """A detected stay-point."""

    lat: float
    lon: float
    arrival_time: datetime
    departure_time: datetime
    duration_minutes: float
    num_points: int = 1
    altitude_m: float = float("nan")  # mean of the valid altitudes in the window; NaN if none
    # Phần của duration_minutes thực sự có điểm GPS: bỏ các khoảng ngắt >
    # unobserved_gap_seconds giữa 2 điểm liên tiếp. None nếu không tính.
    observed_minutes: float | None = None


# ── Detector ────────────────────────────────────────────────────────────────


class StayPointDetector:
    """Detect stay-points from a sorted GPS trajectory.

    Parameters
    ----------
    time_threshold_minutes : int, default 30
        Minimum duration (in minutes) for a segment to qualify as a stay-point.
        30 phút là mốc lớn nhất còn giữ được các lần dừng 30–45 phút; dưới 30
        phút, stay-point giả trong các chuyến xe có nhãn tăng 2–30 lần
        (notebooks/07_staypoint_thresholds.ipynb).
    distance_threshold_meters : int, default 200
        Maximum distance (in meters) for points to qualify as being in the same
        stay region. 200 m bao được độ phân tán lúc đứng yên (P90 trung vị 136 m);
        từ 200 m trở lên độ nhạy và stay-point giả cùng tăng tuyến tính, không có
        mức tối ưu rõ ràng (notebooks/07_staypoint_thresholds.ipynb).
    distance_mode : DistanceMode, default DistanceMode.CENTROID
        - CENTROID: All points in window must be within distance_threshold
          of the RUNNING CENTROID. Centroid is recalculated after each point
          is added to the window, making it more flexible for users who
          move around within a stay region. Các ngưỡng 200 m / 30 phút được
          kiểm chứng ở chế độ này (notebooks 04-08).
        - ANCHOR (Li et al. 2008): All points in window must be within
          distance_threshold of the ANCHOR (first point in window). Cho kết
          quả tương đương trên các chỉ số của notebook 07 (độ nhạy 50.6% so
          với 49.3%, stay-point giả 3.52 so với 3.47 / 100 giờ đi xe).
    unobserved_gap_seconds : float, default 1200
        Khoảng ngắt giữa 2 điểm liên tiếp dài hơn ngưỡng này không được tính vào
        ``observed_minutes`` (vẫn nằm trong ``duration_minutes``). Cùng ngưỡng
        với CleaningThresholds.max_gap_seconds - nằm giữa P99.9 và P99.99 của
        khoảng ngắt bên trong 1 chuyến đi (notebooks/03_segment_gap_threshold.ipynb).
        Khoảng ngắt bên trong stay-point KHÔNG làm cắt stay-point
        (notebooks/06_gaps_inside_staypoints.ipynb).
    max_gap_hours : float or None, default MAX_GAP_HOURS (18)
        Quỹ đạo được cắt tại mọi khoảng ngắt dài hơn ngưỡng này trước khi tìm
        stay-point, nên có thể đưa vào toàn bộ điểm của 1 user (mọi file .plt nối
        lại, hoặc chuỗi điểm của API). Không cắt thì gộp các lần ghi cách nhau
        nhiều ngày/năm thành 1 stay-point; cắt tại mọi ranh giới file thì mất các
        đêm ở nhà (tắt máy buổi tối, bật lại sáng hôm sau). ``None`` = không cắt,
        chỉ dùng để tái hiện cách làm sai trong notebook.
    """

    def __init__(
        self,
        time_threshold_minutes: int = 30,
        distance_threshold_meters: int = 200,
        distance_mode: DistanceMode = DistanceMode.CENTROID,
        unobserved_gap_seconds: float = 1200.0,
        max_gap_hours: float | None = MAX_GAP_HOURS,
    ):
        self.unobserved_gap = pd.Timedelta(seconds=unobserved_gap_seconds)
        self.max_gap = None if max_gap_hours is None else pd.Timedelta(hours=max_gap_hours)
        self.time_threshold = pd.Timedelta(minutes=time_threshold_minutes)
        self.distance_threshold_m = float(distance_threshold_meters)
        self.distance_mode = DistanceMode(distance_mode)

    def _observed_minutes(self, timestamps: list, start_idx: int, end_idx: int) -> float:
        """Tổng các khoảng thời gian giữa 2 điểm liên tiếp trong cửa sổ, bỏ các
        khoảng ngắt > unobserved_gap (thiết bị không ghi)."""
        observed = pd.Timedelta(0)
        for k in range(start_idx, end_idx):
            step = timestamps[k + 1] - timestamps[k]
            if step <= self.unobserved_gap:
                observed += step
        return observed.total_seconds() / 60.0

    def detect(self, trajectory: pd.DataFrame) -> list[StayPoint]:
        """Run stay-point detection on a single trajectory.

        Required columns: ``lat``, ``lon``, ``timestamp`` (datetime).
        Optional column: ``altitude_m`` — averaged into each emitted
        :class:`StayPoint` if present.

        The detection algorithm uses either anchor-based (Li et al. 2008) or
        centroid-based distance calculation, controlled by ``self.distance_mode``.
        """
        if trajectory is None or trajectory.empty:
            return []

        # Normalize column names: datetime -> timestamp (giữ lon như GeoLife gốc)
        df = trajectory.copy()
        if "timestamp" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "timestamp"})

        df = df.sort_values("timestamp").reset_index(drop=True)
        if df.empty or len(df) < 2:
            return []

        ts = pd.to_datetime(df["timestamp"], errors="coerce")
        timestamps = ts.tolist()
        lats = df["lat"].astype(float).tolist()
        lons = df["lon"].astype(float).tolist()
        # Optional altitude column — mean into the emitted StayPoint when present.
        if "altitude_m" in df.columns:
            alts = pd.to_numeric(df["altitude_m"], errors="coerce").tolist()
        elif "altitude" in df.columns:
            # Treat raw feet column as metres-by-assumption so callers that
            # forgot to convert still get a number through; the unit error is
            # documented in the docstring.
            alts = pd.to_numeric(df["altitude"], errors="coerce").tolist()
        else:
            alts = [None] * len(df)

        # Cắt tại các khoảng ngắt > max_gap: cửa sổ không được vượt qua chúng.
        cuts = [] if self.max_gap is None else (np.flatnonzero((ts.diff() > self.max_gap).to_numpy())).tolist()
        edges = [0, *cuts, len(df)]
        detect_part = (self._detect_centroid_based if self.distance_mode == DistanceMode.CENTROID
                       else self._detect_anchor_based)

        stay_points: list[StayPoint] = []
        for a, b in zip(edges[:-1], edges[1:], strict=False):
            part = (timestamps[a:b], lats[a:b], lons[a:b], alts[a:b])
            i = 0
            while i < b - a:
                stay_points, i = detect_part(*part, i, stay_points)
        return stay_points

    def _detect_anchor_based(
        self,
        timestamps: list,
        lats: list[float],
        lons: list[float],
        alts: list,
        start_idx: int,
        stay_points: list[StayPoint],
    ) -> tuple[list[StayPoint], int]:
        """Anchor-based stay-point detection (Li et al. 2008).

        All points in window must be within distance_threshold of the ANCHOR
        (first point in window).
        """
        n = len(lats)
        anchor_lat, anchor_lon = lats[start_idx], lons[start_idx]
        anchor_ts = timestamps[start_idx]

        # expand window to the right while constraints hold
        j = start_idx + 1
        while j < n:
            # Chỉ break khi distance vượt - cho phép time_span >= threshold
            # để qualify. Đây là chuẩn stay-point (Li et al. 2008).
            if haversine_meters(anchor_lat, anchor_lon, lats[j], lons[j]) > self.distance_threshold_m:
                break
            j += 1

        # j là index đầu tiên NGOÀI window (hoặc == n)
        end_idx = j - 1
        window_span = timestamps[end_idx] - anchor_ts

        if window_span >= self.time_threshold:
            stay_points = self._create_stay_point(
                timestamps, lats, lons, alts, start_idx, end_idx, window_span, stay_points
            )
            return stay_points, j  # resume scanning outside the window
        else:
            return stay_points, start_idx + 1  # didn't qualify → advance one step

    def _detect_centroid_based(
        self,
        timestamps: list,
        lats: list[float],
        lons: list[float],
        alts: list,
        start_idx: int,
        stay_points: list[StayPoint],
    ) -> tuple[list[StayPoint], int]:
        """Centroid-based stay-point detection.

        All points in window must be within distance_threshold of the RUNNING CENTROID.
        Centroid is recalculated after each point is added to the window.
        This is more flexible for users who move around within a stay region.
        """
        n = len(lats)

        # Initialize window with the starting point. Tổng cộng dồn theo đúng thứ
        # tự thêm điểm -> kết quả giống hệt sum(list), nhưng O(1) mỗi bước thay vì
        # O(kích thước cửa sổ).
        sum_lat = lats[start_idx]
        sum_lon = lons[start_idx]
        num_pts = 1
        anchor_ts = timestamps[start_idx]
        limit_m = self.distance_threshold_m

        j = start_idx + 1
        while j < n:
            # Khoảng cách từ tâm hiện tại tới điểm j: đúng phép tính của
            # haversine_meters (cùng thứ tự -> cùng kết quả), viết thẳng vào vòng
            # lặp vì đây là chỗ tốn thời gian nhất của detector.
            c_lat = sum_lat / num_pts
            lat_j = lats[j]
            lon_j = lons[j]
            d_lat = radians(lat_j - c_lat)
            d_lon = radians(lon_j - sum_lon / num_pts)
            a = sin(d_lat / 2) ** 2 + cos(radians(c_lat)) * cos(radians(lat_j)) * sin(d_lon / 2) ** 2
            dist_to_centroid = float(EARTH_RADIUS_KM * (2 * asin(sqrt(max(0.0, min(1.0, a)))))) * 1000.0
            if dist_to_centroid > limit_m:
                break

            sum_lat += lat_j
            sum_lon += lon_j
            num_pts += 1
            j += 1

        # j là index đầu tiên NGOÀI window (hoặc == n)
        end_idx = j - 1
        window_span = timestamps[end_idx] - anchor_ts

        if window_span >= self.time_threshold:
            final_centroid_lat = sum_lat / num_pts
            final_centroid_lon = sum_lon / num_pts
            mean_alt = _mean_altitude(alts[start_idx:end_idx + 1])

            stay_points.append(
                StayPoint(
                    lat=final_centroid_lat,
                    lon=final_centroid_lon,
                    arrival_time=anchor_ts.to_pydatetime() if hasattr(anchor_ts, "to_pydatetime") else anchor_ts,
                    departure_time=(timestamps[end_idx].to_pydatetime() if hasattr(timestamps[end_idx], "to_pydatetime") else timestamps[end_idx]),
                    duration_minutes=window_span.total_seconds() / 60.0,
                    num_points=num_pts,
                    altitude_m=mean_alt,
                    observed_minutes=self._observed_minutes(timestamps, start_idx, end_idx),
                )
            )
            return stay_points, j  # resume scanning outside the window
        else:
            return stay_points, start_idx + 1  # didn't qualify → advance one step

    def _create_stay_point(
        self,
        timestamps: list,
        lats: list[float],
        lons: list[float],
        alts: list,
        start_idx: int,
        end_idx: int,
        window_span,
        stay_points: list[StayPoint],
    ) -> list[StayPoint]:
        """Create a StayPoint from window data. Used by anchor-based detection."""
        window_lat = lats[start_idx : end_idx + 1]
        window_lon = lons[start_idx : end_idx + 1]
        window_alt = alts[start_idx : end_idx + 1]
        num_pts = end_idx - start_idx + 1

        # Centroid (arithmetic mean of lat/lon — adequate for short distances).
        centroid_lat = float(sum(window_lat) / num_pts)
        centroid_lon = float(sum(window_lon) / num_pts)

        # Mean altitude over the window, ignoring None / NaN.
        mean_alt = _mean_altitude(window_alt)

        anchor_ts = timestamps[start_idx]

        stay_points.append(
            StayPoint(
                lat=centroid_lat,
                lon=centroid_lon,
                arrival_time=anchor_ts.to_pydatetime() if hasattr(anchor_ts, "to_pydatetime") else anchor_ts,
                departure_time=(timestamps[end_idx].to_pydatetime() if hasattr(timestamps[end_idx], "to_pydatetime") else timestamps[end_idx]),
                duration_minutes=window_span.total_seconds() / 60.0,
                num_points=num_pts,
                altitude_m=mean_alt,
                observed_minutes=self._observed_minutes(timestamps, start_idx, end_idx),
            )
        )
        return stay_points


# ── Tabular output ──────────────────────────────────────────────────────────

STAY_POINT_COLUMNS = [
    "user_id", "arrival", "departure", "arrival_local", "departure_local", "tz_name",
    "lat", "lon", "duration_minutes", "observed_minutes", "num_points", "altitude_m",
]


def stay_points_to_frame(stay_points: list[StayPoint], user_id: str) -> pd.DataFrame:
    """Bảng stay-point của 1 user, schema ``STAY_POINT_COLUMNS``.

    ``arrival`` / ``departure`` là GMT naive như dữ liệu GeoLife. Giờ địa phương
    (naive) và ``tz_name`` lấy theo múi giờ của **tâm** stay-point
    (notebooks/09_timezone_by_location.ipynb), nên dùng được cả khi đầu vào chỉ có
    lat/lon/giờ GMT (API), không cần cột ``timestamp_local`` của từng điểm.
    """
    from gps.data.timezone import localize_by_location

    df = pd.DataFrame(
        [{"user_id": user_id, "arrival": pd.Timestamp(sp.arrival_time), "departure": pd.Timestamp(sp.departure_time),
          "lat": sp.lat, "lon": sp.lon, "duration_minutes": sp.duration_minutes,
          "observed_minutes": sp.observed_minutes, "num_points": sp.num_points, "altitude_m": sp.altitude_m}
         for sp in stay_points],
        columns=[c for c in STAY_POINT_COLUMNS if c not in ("arrival_local", "departure_local", "tz_name")],
    )
    if df.empty:
        return df.reindex(columns=STAY_POINT_COLUMNS).astype(
            {"arrival": "datetime64[ns]", "departure": "datetime64[ns]", "arrival_local": "datetime64[ns]",
             "departure_local": "datetime64[ns]", "tz_name": object, "lat": float, "lon": float,
             "duration_minutes": float, "observed_minutes": float, "num_points": "int64", "altitude_m": float})
    df = localize_by_location(df, column="arrival", output_column="arrival_local")
    df = localize_by_location(df, column="departure", output_column="departure_local")
    return df[STAY_POINT_COLUMNS]
