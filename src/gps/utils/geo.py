"""Geographic utilities — Haversine + centroid helpers.

Single source of truth for distance / centroid math used across the pipeline.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Mean Earth radius (km) — matches GPSCleaner legacy value to keep test parity.
EARTH_RADIUS_KM = 6371.0088


# ── Distance (Haversine, scalar) ─────────────────────────────────────────────


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two WGS84 points (kilometers)."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))
    return float(EARTH_RADIUS_KM * c)


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Convenience wrapper in meters."""
    return haversine_km(lat1, lng1, lat2, lng2) * 1000.0


# ── Distance / Speed (vectorized over a DataFrame) ───────────────────────────


def haversine_vector_km(df: pd.DataFrame, lat_col: str = "lat", lng_col: str = "lng") -> np.ndarray:
    """Distance in km between each row and its predecessor.

    First row returns ``np.nan`` (no predecessor).
    Output array aligns positionally with ``df.index``.
    """
    if len(df) < 2:
        return np.full(len(df), np.nan)

    lat1 = np.radians(df[lat_col].to_numpy(dtype=float))
    lat2 = np.radians(df[lat_col].shift(1).to_numpy(dtype=float))
    dlat = lat1 - lat2
    dlng = np.radians(df[lng_col].to_numpy(dtype=float)) - np.radians(
        df[lng_col].shift(1).to_numpy(dtype=float)
    )

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat2) * np.cos(lat1) * np.sin(dlng / 2.0) ** 2
    a = np.where(np.isnan(a), 0.0, a)
    a = np.clip(a, 0.0, 1.0)
    c = 2.0 * np.arcsin(np.sqrt(a))
    distance_km = EARTH_RADIUS_KM * c
    distance_km[0] = np.nan
    return distance_km


def haversine_vector_meters(
    df: pd.DataFrame, lat_col: str = "lat", lng_col: str = "lng"
) -> np.ndarray:
    """Same as :func:`haversine_vector_km` but in meters."""
    return haversine_vector_km(df, lat_col, lng_col) * 1000.0


def speed_kmh(df: pd.DataFrame, distance_km_col: str = "distance_km", time_col: str = "delta_time_s") -> np.ndarray:
    """Vectorized km/h given precomputed distance (km) and time delta (s)."""
    if len(df) < 2:
        return np.full(len(df), np.nan)

    d = df[distance_km_col].to_numpy(dtype=float)
    t = df[time_col].to_numpy(dtype=float)
    t = np.where((t <= 0) | np.isnan(t), np.nan, t)

    speed = (d / t) * 3600.0
    speed[0] = np.nan
    return speed


# ── Centroid (single & batch) ────────────────────────────────────────────────


def centroid_lat_lng(points: pd.DataFrame) -> tuple[float, float]:
    """Plain arithmetic mean of lat/lng — adequate for short distances (<10 km)."""
    if points is None or points.empty:
        return 0.0, 0.0
    return float(points["lat"].mean()), float(points["lng"].mean())
