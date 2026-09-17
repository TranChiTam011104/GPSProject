"""Unit tests for GPS cleaner."""
import pytest
from src.data.cleaner import GPSCleaner, CleaningConfig


class TestGPSCleaner:
    """Tests for GPSCleaner."""

    def test_initialization(self):
        """Test cleaner initialization."""
        cleaner = GPSCleaner()
        assert cleaner.config.max_speed_kmh == 300.0

    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        config = CleaningConfig(max_speed_kmh=200.0)
        cleaner = GPSCleaner(config)
        assert cleaner.config.max_speed_kmh == 200.0

    def test_haversine_distance_zero(self):
        """Test distance for same point."""
        distance = GPSCleaner.haversine_distance(39.9847, 116.3184, 39.9847, 116.3184)
        assert distance == 0

    def test_haversine_distance_known(self):
        """Test distance between known points."""
        # Beijing to Shanghai (~1067 km)
        distance = GPSCleaner.haversine_distance(
            39.9847, 116.3184,
            31.2304, 121.4737
        )
        assert 1000 < distance < 1100

    def test_calculate_speed(self):
        """Test speed calculation."""
        speed = GPSCleaner.calculate_speed(
            distance_km=100,
            time_diff_seconds=3600  # 1 hour
        )
        assert speed == 100.0
