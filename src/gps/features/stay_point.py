"""Stay-point detection (Checkpoint 1 / Tuần 1).

Algorithm — sliding-window over a sorted GPS trajectory:

1. Walk the trajectory by index ``i`` (anchor).
2. Keep expanding the right end of the window while
   - the cumulative time delta stays below ``time_threshold`` AND
   - every point in the window is within ``distance_threshold`` of the anchor.
3. If the window covers at least ``time_threshold`` → emit one stay-point
   anchored at the centroid of the window.
4. Resume scanning from the first point *outside* the window.

Returns a list of :class:`StayPoint`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List

import pandas as pd

from gps.utils.geo import haversine_meters


# ── Output value objects ─────────────────────────────────────────────────────


@dataclass
class StayPoint:
    """A detected stay-point."""

    lat: float
    lng: float
    arrival_time: datetime
    departure_time: datetime
    duration_minutes: float
    num_points: int = 1
    altitude_m: float = 0.0  # mean of the points inside the stay-point window
    accuracy: float = 0.0    # mean GPS accuracy inside the window (if available)

    @property
    def center_lat(self) -> float:
        return self.lat

    @property
    def center_lng(self) -> float:
        return self.lng

    @property
    def start_time(self) -> datetime:
        return self.arrival_time

    @property
    def end_time(self) -> datetime:
        return self.departure_time

    @property
    def n_points(self) -> int:
        return self.num_points


# ── Detector ────────────────────────────────────────────────────────────────


class StayPointDetector:
    """Detect stay-points from a sorted GPS trajectory."""

    def __init__(
        self,
        time_threshold_minutes: int = 30,
        distance_threshold_meters: int = 200,
    ):
        self.time_threshold = pd.Timedelta(minutes=time_threshold_minutes)
        # Legacy attribute name kept for unit-test parity.
        self.distance_threshold = float(distance_threshold_meters)
        self.distance_threshold_m = float(distance_threshold_meters)
        # Bytes-as-attribute (when callers treat threshold as timedelta/seconds).
        self.time_threshold_seconds = self.time_threshold.total_seconds()

    # ── Backwards-compat helpers (unit-tested) ───────────────────────────────

    def _haversine_meters(self, lat1, lng1, lat2, lng2) -> float:
        return haversine_meters(lat1, lng1, lat2, lng2)

    def _calculate_centroid(self, points):
        if points is None or points.empty:
            return 0.0, 0.0
        return float(points["lat"].mean()), float(points["lng"].mean())

    def detect(self, trajectory: pd.DataFrame) -> List[StayPoint]:
        """Run stay-point detection on a single trajectory.

        Required columns: ``lat``, ``lng``, ``timestamp`` (datetime).
        Optional column: ``altitude_m`` — averaged into each emitted
        :class:`StayPoint` if present.
        """
        if trajectory is None or trajectory.empty:
            return []

        df = trajectory.sort_values("timestamp").reset_index(drop=True)
        if df.empty or len(df) < 2:
            return []

        timestamps = pd.to_datetime(df["timestamp"], errors="coerce").tolist()
        lats = df["lat"].astype(float).tolist()
        lngs = df["lng"].astype(float).tolist()
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

        stay_points: List[StayPoint] = []
        n = len(df)
        i = 0
        while i < n:
            anchor_lat, anchor_lng = lats[i], lngs[i]
            anchor_ts = timestamps[i]

            # expand window to the right while constraints hold
            j = i + 1
            while j < n:
                span = timestamps[j] - anchor_ts
                if span >= self.time_threshold:
                    break
                if haversine_meters(anchor_lat, anchor_lng, lats[j], lngs[j]) > self.distance_threshold_m:
                    break
                j += 1

            # j is the first index outside the window (or == n)
            end_idx = j - 1
            window_span = timestamps[end_idx] - anchor_ts
            if window_span >= self.time_threshold:
                window_lat = lats[i : end_idx + 1]
                window_lng = lngs[i : end_idx + 1]
                window_alt = alts[i : end_idx + 1]
                num_pts = end_idx - i + 1

                # Centroid (arithmetic mean of lat/lng — adequate for short distances).
                centroid_lat = float(sum(window_lat) / num_pts)
                centroid_lng = float(sum(window_lng) / num_pts)

                # Mean altitude over the window, ignoring None / NaN.
                alt_values = [a for a in window_alt if a is not None and a == a]
                mean_alt = float(sum(alt_values) / len(alt_values)) if alt_values else 0.0

                stay_points.append(
                    StayPoint(
                        lat=centroid_lat,
                        lng=centroid_lng,
                        arrival_time=anchor_ts.to_pydatetime() if hasattr(anchor_ts, "to_pydatetime") else anchor_ts,
                        departure_time=(timestamps[end_idx].to_pydatetime() if hasattr(timestamps[end_idx], "to_pydatetime") else timestamps[end_idx]),
                        duration_minutes=window_span.total_seconds() / 60.0,
                        num_points=num_pts,
                        altitude_m=mean_alt,
                    )
                )
                i = j  # resume scanning outside the window
            else:
                i += 1  # didn't qualify → advance one step

        return stay_points

    def detect_batch(self, trajectories: Iterable[pd.DataFrame]) -> List[List[StayPoint]]:
        return [self.detect(t) for t in trajectories]
