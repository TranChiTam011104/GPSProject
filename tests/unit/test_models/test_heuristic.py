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
        assert classifier.home_hour_end == 8

    def test_initialization_with_config(self, model_config):
        """Test initialization with custom config."""
        classifier = HeuristicClassifier(model_config)
        assert classifier.home_hour_start == 22

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


class TestWindowMinutes:
    """Score = minutes of the stay inside the daily window, in local time (notebook 12)."""

    def test_overnight_stay_arriving_before_window_is_home(self):
        # Wednesday 20:00 -> Thursday 07:00 local: 22:00-07:00 = 9 h inside 22-08.
        home, office = HeuristicClassifier().window_minutes(datetime(2008, 10, 22, 20, 0), datetime(2008, 10, 23, 7, 0))
        assert home == 9 * 60
        assert office == 0

    def test_stay_covering_both_windows(self):
        # Wednesday 07:00 -> 19:00: 1 h of home window (07-08), 9 h of office window (09-18).
        home, office = HeuristicClassifier().window_minutes(datetime(2008, 10, 22, 7, 0), datetime(2008, 10, 22, 19, 0))
        assert (home, office) == (60, 9 * 60)

    def test_office_ignores_weekend(self):
        # Saturday 2008-10-25 10:00 -> 16:00.
        home, office = HeuristicClassifier().window_minutes(datetime(2008, 10, 25, 10, 0), datetime(2008, 10, 25, 16, 0))
        assert (home, office) == (0, 0)

    def test_multi_day_stay_counts_every_day(self):
        # Wednesday 00:00 -> Friday 00:00: two full days.
        home, office = HeuristicClassifier().window_minutes(datetime(2008, 10, 22), datetime(2008, 10, 24))
        assert home == 2 * 10 * 60            # 00-08 and 22-24 each day
        assert office == 2 * 9 * 60


class TestWinner:
    @staticmethod
    def _stay(lat, lon, arrival_local_beijing, hours):
        """Stay in Beijing given in local time (GMT+8 in October)."""
        arrival = arrival_local_beijing - timedelta(hours=8)
        return {"lat": lat, "lon": lon, "arrival_time": arrival, "departure_time": arrival + timedelta(hours=hours)}

    def test_stay_arriving_before_22_is_home(self):
        # The arrival-hour rule used to miss this one: arrival 20:00 is outside 22-08.
        result = HeuristicClassifier().predict([self._stay(39.98, 116.31, datetime(2008, 10, 22, 20, 0), 11)])
        assert result.home is not None
        assert result.home.confidence == 1.0

    def test_most_minutes_in_window_wins(self):
        short = self._stay(39.98, 116.31, datetime(2008, 10, 22, 23, 0), 2)        # 2 h in window
        long = self._stay(39.90, 116.40, datetime(2008, 10, 23, 22, 0), 9)         # 9 h in window
        result = HeuristicClassifier().predict([short, long])
        assert (result.home.lat, result.home.lon) == (39.90, 116.40)
        assert result.home.confidence == 9 / 11

    def test_tie_goes_to_longer_then_earlier_stay(self):
        night = self._stay(39.98, 116.31, datetime(2008, 10, 22, 22, 0), 10)       # 10 h in window, 10 h long
        longer = self._stay(39.90, 116.40, datetime(2008, 10, 23, 22, 0), 12)      # 10 h in window, 12 h long
        assert HeuristicClassifier().predict([night, longer]).home.lat == 39.90
        later = self._stay(39.98, 116.31, datetime(2008, 10, 24, 22, 0), 10)       # same as ``night``, a day later
        assert HeuristicClassifier().predict([later, night]).home.lat == 39.98

    def test_poi_is_stay_outside_both_windows(self):
        # Saturday 12:00-15:00: no home minutes, no office minutes (weekend).
        result = HeuristicClassifier().predict([self._stay(39.95, 116.35, datetime(2008, 10, 25, 12, 0), 3)])
        assert result.home is None
        assert result.office is None
        assert len(result.pois) == 1
