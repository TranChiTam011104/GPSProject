"""
Clustering algorithms for location grouping.

Uses DBSCAN to group nearby stay-points into locations,
reducing noise from GPS drift.
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler


@dataclass
class LocationCluster:
    """Represents a clustered location from multiple stay-points."""
    cluster_id: int
    centroid_lat: float
    centroid_lng: float
    num_points: int
    total_duration_minutes: float
    stay_points: List = field(default_factory=list)
    
    @property
    def avg_duration(self) -> float:
        """Average duration per stay-point in the cluster."""
        if self.num_points == 0:
            return 0.0
        return self.total_duration_minutes / self.num_points


class LocationClusterer:
    """
    Cluster nearby stay-points using DBSCAN.
    
    DBSCAN is chosen because:
    1. No need to specify number of clusters upfront
    2. Can find clusters of arbitrary shape
    3. Resistant to outliers
    4. Works well with geographic coordinates
    """

    def __init__(
        self,
        eps_meters: float = 100.0,
        min_samples: int = 3
    ):
        self.eps_meters = eps_meters
        self.min_samples = min_samples
        
    def fit_predict(self, stay_points: pd.DataFrame) -> np.ndarray:
        """
        Cluster stay-points.
        
        Args:
            stay_points: DataFrame with columns:
                - lat: Latitude
                - lng: Longitude
                - duration_minutes: Duration at stay-point
                
        Returns:
            Array of cluster labels (-1 for noise)
        """
        pass  # TODO: Implement

    def cluster_to_locations(
        self, 
        stay_points: pd.DataFrame,
        labels: np.ndarray
    ) -> List[LocationCluster]:
        """
        Convert cluster labels to LocationCluster objects.
        
        Args:
            stay_points: DataFrame with stay-point data
            labels: Cluster labels from fit_predict
            
        Returns:
            List of LocationCluster objects
        """
        pass  # TODO: Implement

    def _haversine_to_radians(self, meters: float) -> float:
        """
        Convert meters to radians for haversine metric.
        
        Args:
            meters: Distance in meters
            
        Returns:
            Distance in radians
        """
        import math
        earth_radius = 6371000  # meters
        return meters / earth_radius

    def cluster_single_location(
        self, 
        stay_points: pd.DataFrame
    ) -> LocationCluster:
        """
        Cluster a single user's stay-points into locations.
        
        Args:
            stay_points: DataFrame with columns: lat, lng, duration_minutes
            
        Returns:
            List of LocationCluster objects
        """
        pass  # TODO: Implement

    def merge_clusters(
        self, 
        clusters: List[LocationCluster],
        distance_threshold_meters: float = 50.0
    ) -> List[LocationCluster]:
        """
        Merge nearby clusters that likely represent the same location.
        
        Args:
            clusters: List of location clusters
            distance_threshold_meters: Maximum distance to merge
            
        Returns:
            List of merged clusters
        """
        pass  # TODO: Implement


def evaluate_clustering(
    stay_points: pd.DataFrame,
    labels: np.ndarray,
    metrics: List[str] = ["silhouette", "davies_bouldin"]
) -> dict:
    """
    Evaluate clustering quality.
    
    Args:
        stay_points: Stay-point DataFrame
        labels: Cluster labels
        metrics: List of metrics to compute
        
    Returns:
        Dictionary of metric names to values
    """
    pass  # TODO: Implement
