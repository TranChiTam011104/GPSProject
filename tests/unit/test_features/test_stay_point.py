"""Unit tests for stay-point detection."""
import pytest
from datetime import datetime, timedelta
from src.features.stay_point import StayPointDetector, StayPoint


class TestStayPointDetector:
    """Tests for StayPointDetector."""

    def test_detector_initialization(self):
        """Test detector can be initialized."""
        detector = StayPointDetector(
            time_threshold_minutes=30,
            distance_threshold_meters=200
        )
        assert detector.time_threshold == timedelta(minutes=30)
        assert detector.distance_threshold == 200

    def test_haversine_distance_calculation(self):
        """Test distance calculation between two points."""
        detector = StayPointDetector()
        
        # Beijing to Shanghai (~1067 km)
        distance = detector._haversine_meters(
            39.9847, 116.3184,
            31.2304, 121.4737
        )
        
        assert 1_000_000 < distance < 1_100_000  # ~1067 km

    def test_detect_returns_list(self, sample_trajectory):
        """Test detection returns a list."""
        detector = StayPointDetector()
        result = detector.detect(sample_trajectory)
        assert isinstance(result, list)

    def test_calculate_centroid(self):
        """Test centroid calculation."""
        import pandas as pd
        detector = StayPointDetector()
        
        points = pd.DataFrame({
            "lat": [39.9847, 39.9848, 39.9849],
            "lng": [116.3184, 116.3185, 116.3186]
        })
        
        lat, lng = detector._calculate_centroid(points)
        assert lat == pytest.approx(39.9848, abs=1e-6)
        assert lng == pytest.approx(116.3185, abs=1e-6)
