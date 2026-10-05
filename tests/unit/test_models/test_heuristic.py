"""Unit tests for heuristic classifier."""
from datetime import datetime, timedelta

from gps.models.base import ClassificationResult
from gps.models.heuristic import HeuristicClassifier


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
        assert isinstance(result, ClassificationResult)


class TestLocalTime:
    """Hour rules use local time from the stay's location (notebook 09), not the GMT input."""

    @staticmethod
    def _stay(lat, lon, arrival_gmt, hours):
        return {"lat": lat, "lon": lon, "arrival_time": arrival_gmt,
                "departure_time": arrival_gmt + timedelta(hours=hours)}

    def test_beijing_night_is_home_not_office(self):
        # 2008-10-22 is a Wednesday. 14:30 GMT = 22:30 in Beijing: at home, not at work.
        result = HeuristicClassifier().predict([self._stay(39.9847, 116.3184, datetime(2008, 10, 22, 14, 30), 8)])
        assert result.home is not None
        assert result.office is None

    def test_beijing_office_hours_in_gmt_morning(self):
        # 01:00 GMT Wednesday = 09:00 in Beijing.
        result = HeuristicClassifier().predict([self._stay(40.0043, 116.3263, datetime(2008, 10, 22, 1, 0), 9)])
        assert result.office is not None
        assert result.home is None

    def test_seattle_uses_its_own_time_zone(self):
        # 06:00 GMT = 23:00 in Seattle (summer time, GMT-7).
        result = HeuristicClassifier().predict([self._stay(47.6062, -122.3321, datetime(2008, 7, 2, 6, 0), 8)])
        assert result.home is not None
