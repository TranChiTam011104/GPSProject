"""Unit tests for heuristic classifier."""
import pytest
from src.models.heuristic import HeuristicClassifier
from src.models.base import ClassificationResult


class TestHeuristicClassifier:
    """Tests for HeuristicClassifier."""

    def test_initialization(self):
        """Test classifier can be initialized."""
        classifier = HeuristicClassifier()
        assert classifier.home_hour_start == 22
        assert classifier.home_hour_end == 6

    def test_initialization_with_config(self, model_config):
        """Test initialization with custom config."""
        classifier = HeuristicClassifier(model_config)
        assert classifier.home_hour_start == 22

    def test_is_home_time(self):
        """Test home time detection."""
        classifier = HeuristicClassifier()
        
        # 23:00 should be home time
        assert classifier._is_home_time(datetime(2024, 1, 1, 23, 0))
        
        # 03:00 should be home time
        assert classifier._is_home_time(datetime(2024, 1, 1, 3, 0))
        
        # 12:00 should not be home time
        assert not classifier._is_home_time(datetime(2024, 1, 1, 12, 0))

    def test_is_office_time(self):
        """Test office time detection."""
        classifier = HeuristicClassifier()
        
        # Monday 10:00 should be office time
        monday_10am = datetime(2024, 1, 1, 10, 0)  # Monday
        assert classifier._is_office_time(monday_10am)
        
        # Monday 22:00 should not be office time
        assert not classifier._is_office_time(datetime(2024, 1, 1, 22, 0))
        
        # Saturday 10:00 should not be office time
        assert not classifier._is_office_time(datetime(2024, 1, 6, 10, 0))

    def test_model_version(self):
        """Test model version identifier."""
        classifier = HeuristicClassifier()
        assert classifier.get_model_version() == "v1-heuristic"

    def test_predict_returns_result(self, sample_stay_points):
        """Test predict returns ClassificationResult."""
        classifier = HeuristicClassifier()
        result = classifier.predict(sample_stay_points)
        # When implemented, this should return a ClassificationResult
        # For now just check it doesn't crash
