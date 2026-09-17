"""
Stay-point detection algorithm.

A stay-point is a location where a user spends a significant amount of time,
determined by:
- Time threshold: minimum time spent at a location
- Distance threshold: maximum distance from the reference point
"""
import pandas as pd
import numpy as np
from typing import Tuple, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class StayPoint:
    """Represents a detected stay-point."""
    lat: float
    lng: float
    arrival_time: datetime
    departure_time: datetime
    duration_minutes: float
    num_visits: int = 1
    
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


class StayPointDetector:
    """
    Detect stay-points from GPS trajectories.
    
    Algorithm:
    1. For each point in trajectory, find points within distance threshold
    2. If time between first and last point exceeds time threshold, mark as stay-point
    3. Return centroid of all points in the stay-point
    """

    def __init__(
        self,
        time_threshold_minutes: int = 30,
        distance_threshold_meters: int = 200
    ):
        self.time_threshold = timedelta(minutes=time_threshold_minutes)
        self.distance_threshold = distance_threshold_meters
        
    def detect(self, trajectory: pd.DataFrame) -> List[StayPoint]:
        """
        Detect stay-points in a GPS trajectory.
        
        Args:
            trajectory: DataFrame with columns:
                - lat: Latitude
                - lng: Longitude  
                - timestamp: Datetime timestamp
                
        Returns:
            List of detected StayPoint objects
        """
        pass  # TODO: Implement

    def _haversine_meters(
        self, 
        lat1: float, lng1: float, 
        lat2: float, lng2: float
    ) -> float:
        """
        Calculate distance between two points in meters.
        
        Args:
            lat1, lng1: First point coordinates
            lat2, lng2: Second point coordinates
            
        Returns:
            Distance in meters
        """
        pass  # TODO: Implement

    def _calculate_centroid(
        self, 
        points: pd.DataFrame
    ) -> Tuple[float, float]:
        """
        Calculate centroid of a group of points.
        
        For geographic data, we use the mean of lat/lng.
        More accurate methods might use weighted centroids or
        spherical averaging.
        
        Args:
            points: DataFrame with lat, lng columns
            
        Returns:
            Tuple of (centroid_lat, centroid_lng)
        """
        pass  # TODO: Implement

    def detect_batch(
        self, 
        trajectories: List[pd.DataFrame]
    ) -> List[List[StayPoint]]:
        """
        Detect stay-points in multiple trajectories.
        
        Args:
            trajectories: List of trajectory DataFrames
            
        Returns:
            List of stay-point lists, one per trajectory
        """
        return [self.detect(traj) for traj in trajectories]


def tune_thresholds(
    trajectories: List[pd.DataFrame],
    time_range: Tuple[int, int] = (10, 60),
    distance_range: Tuple[int, int] = (50, 500),
    step: int = 10
) -> Tuple[int, int]:
    """
    Tune stay-point detection thresholds.
    
    Args:
        trajectories: List of trajectory DataFrames
        time_range: (min, max) time threshold in minutes
        distance_range: (min, max) distance threshold in meters
        step: Step size for grid search
        
    Returns:
        Tuple of (best_time_threshold, best_distance_threshold)
    """
    pass  # TODO: Implement
