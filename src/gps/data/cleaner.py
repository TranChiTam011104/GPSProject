"""GPS data cleaning utilities (Checkpoint 1 / Tuần 1).

Backbone of the GeoLife preprocessing pipeline:

- ``clean_trajectory`` — drop invalid rows, dedupe timestamps, sort, then run
  the speed- and distance-based filters.
- ``filter_by_speed`` / ``filter_by_distance`` — pure vectorised Haversine
  implementations (wrappers around :mod:`gps.utils.geo`).
- ``split_by_gaps`` — break trajectories when the time gap exceeds
  ``max_time_gap_hours`` (the stay-point detector cannot bridge across them).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from gps.utils.geo import (
    EARTH_RADIUS_KM,
    haversine_km,
    haversine_vector_km,
)


@dataclass
class CleaningConfig:
    """Tuning knobs for the cleaner."""

    max_speed_kmh: float = 300.0   # anything faster is a GPS glitch
    max_jump_km: float = 50.0      # max plausible jump between two consecutive points
    max_time_gap_hours: float = 6.0
    min_points: int = 10


class GPSCleaner:
    """Clean GPS traces by removing noise and invalid points."""

    EARTH_RADIUS_KM = EARTH_RADIUS_KM

    def __init__(self, config: Optional[CleaningConfig] = None):
        self.config = config or CleaningConfig()

    # ── Public ───────────────────────────────────────────────────────────────

    def clean_trajectory(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        df = df.copy()

        required = {"lat", "lng", "timestamp"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        df = df[
            (df["lat"].between(-90, 90))
            & (df["lng"].between(-180, 180))
            & df["lat"].notna()
            & df["lng"].notna()
        ].copy()
        if df.empty:
            return df

        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        if df.empty:
            return df

        df = df.sort_values("timestamp").drop_duplicates(subset="timestamp")
        df = df.reset_index(drop=True)

        df = self.filter_by_distance(df)
        df = self.filter_by_speed(df)
        df = df.reset_index(drop=True)
        return df

    def filter_by_speed(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < 2:
            return df
        df = df.copy().reset_index(drop=True)
        distance_km = haversine_vector_km(df)
        time_diff = df["timestamp"].diff().dt.total_seconds()
        time_diff = time_diff.where(time_diff > 0)
        speed_kmh = (distance_km / time_diff) * 3600.0

        first_ok = np.zeros(len(speed_kmh), dtype=bool)
        first_ok[0] = True
        mask_ok = first_ok | (speed_kmh <= self.config.max_speed_kmh)
        return df[mask_ok].copy()

    def filter_by_distance(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < 2:
            return df
        df = df.copy().reset_index(drop=True)
        distance_km = haversine_vector_km(df)

        first_ok = np.zeros(len(distance_km), dtype=bool)
        first_ok[0] = True
        mask_ok = first_ok | (distance_km <= self.config.max_jump_km)
        return df[mask_ok].copy()

    def split_by_gaps(self, df: pd.DataFrame) -> List[pd.DataFrame]:
        if df is None or df.empty:
            return []
        df = df.sort_values("timestamp").reset_index(drop=True)
        if len(df) < 2:
            return [df] if len(df) >= self.config.min_points else []

        gap = df["timestamp"].diff().dt.total_seconds() / 3600.0
        split_idx = gap > self.config.max_time_gap_hours
        group_id = split_idx.cumsum()
        return [
            group.reset_index(drop=True)
            for _, group in df.groupby(group_id)
            if len(group) >= self.config.min_points
        ]

    # ── Statics (legacy public API) ──────────────────────────────────────────

    @staticmethod
    def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        return haversine_km(lat1, lng1, lat2, lng2)

    @staticmethod
    def calculate_speed(distance_km: float, time_diff_seconds: float) -> float:
        if time_diff_seconds <= 0:
            return 0.0
        return float((distance_km / time_diff_seconds) * 3600.0)
