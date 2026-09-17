"""
Thresholds for stay-point detection and classification.
"""
from dataclasses import dataclass


@dataclass
class StayPointThresholds:
    """Thresholds for stay-point detection algorithm."""

    # Time threshold: minimum time spent at a location to be considered a stay-point
    time_threshold_minutes: int = 30

    # Distance threshold: maximum distance to move before leaving a stay-point
    distance_threshold_meters: int = 200

    # Convert to radians for haversine calculation
    @property
    def distance_threshold_radians(self) -> float:
        """Convert meters to radians for haversine."""
        import math
        # Earth's radius in meters
        earth_radius = 6371000
        return self.distance_threshold_meters / earth_radius


@dataclass
class ClusteringThresholds:
    """Thresholds for DBSCAN clustering."""

    # Maximum distance between two samples to be considered neighbors
    eps_meters: float = 100.0

    # Minimum number of samples in a neighborhood to form a core point
    min_samples: int = 3

    @property
    def eps_radians(self) -> float:
        """Convert meters to radians for haversine."""
        import math
        earth_radius = 6371000
        return self.eps_meters / earth_radius


@dataclass
class ClassificationThresholds:
    """Thresholds for home/office classification."""

    # Home hours (night time)
    home_hour_start: int = 22  # 10 PM
    home_hour_end: int = 6     # 6 AM

    # Office hours (work hours)
    office_hour_start: int = 9  # 9 AM
    office_hour_end: int = 18    # 6 PM

    # Work days (Monday = 0, Sunday = 6)
    work_days: tuple = (0, 1, 2, 3, 4)

    # Minimum confidence to accept classification
    min_confidence: float = 0.3


# Default threshold configurations
STAY_POINT_THRESHOLDS = StayPointThresholds()
CLUSTERING_THRESHOLDS = ClusteringThresholds()
CLASSIFICATION_THRESHOLDS = ClassificationThresholds()
