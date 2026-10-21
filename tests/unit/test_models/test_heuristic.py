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
        # Two nights at the same place, so the answer is not a one-off.
        nights = [self._stay(39.9847, 116.3184, datetime(2008, 10, d, 14, 30), 8) for d in (22, 23)]
        result = HeuristicClassifier().predict(nights)
        assert result.home is not None
        assert result.office is None

    def test_beijing_office_hours_in_gmt_morning(self):
        # 01:00 GMT Wednesday = 09:00 in Beijing.
        days = [self._stay(40.0043, 116.3263, datetime(2008, 10, d, 1, 0), 9) for d in (22, 23)]
        result = HeuristicClassifier().predict(days)
        assert result.office is not None
        assert result.home is None

    def test_seattle_uses_its_own_time_zone(self):
        # 06:00 GMT = 23:00 in Seattle (summer time, GMT-7).
        nights = [self._stay(47.6062, -122.3321, datetime(2008, 7, d, 6, 0), 8) for d in (2, 3)]
        assert HeuristicClassifier().predict(nights).home is not None


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
        # The arrival-hour rule used to miss these: arrival 20:00 is outside 22-08.
        nights = [self._stay(39.98, 116.31, datetime(2008, 10, d, 20, 0), 11) for d in (22, 23)]
        result = HeuristicClassifier().predict(nights)
        assert result.home is not None
        assert result.home.confidence == 0.5          # two equal nights: 600 of 1200 window minutes

    def test_most_minutes_in_window_wins(self):
        # The winner has to repeat inside the window, so each place is visited twice.
        short = [self._stay(39.98, 116.31, datetime(2008, 10, d, 23, 0), 5) for d in (22, 24)]   # 5 h in window
        long = [self._stay(39.90, 116.40, datetime(2008, 10, d, 22, 0), 9) for d in (23, 25)]    # 9 h in window
        result = HeuristicClassifier().predict(short + long)
        assert (result.home.lat, result.home.lon) == (39.90, 116.40)
        assert result.home.confidence == 9 / 28

    def test_tie_goes_to_longer_then_earlier_stay(self):
        def two(lat, lon, first_day, hours):
            return [self._stay(lat, lon, datetime(2008, 10, d, 22, 0), hours) for d in (first_day, first_day + 2)]

        night = two(39.98, 116.31, 22, 10)       # 10 h in window, 10 h long
        longer = two(39.90, 116.40, 23, 12)      # 10 h in window, 12 h long
        assert HeuristicClassifier().predict(night + longer).home.lat == 39.90
        later = two(39.98, 116.31, 24, 10)       # same as ``night``, later
        assert HeuristicClassifier().predict(later + night).home.lat == 39.98

    def test_poi_is_stay_outside_both_windows(self):
        # Saturday 12:00-15:00: no home minutes, no office minutes (weekend).
        result = HeuristicClassifier().predict([self._stay(39.95, 116.35, datetime(2008, 10, 25, 12, 0), 3)])
        assert result.home is None
        assert result.office is None
        assert len(result.pois) == 1


class TestUnknown:
    """Unknown results and the evidence kept with them (notebooks/13_minimum_evidence.ipynb)."""

    @staticmethod
    def _night(lat, lon, day, hours=10, start_hour=22):
        """Stay in Beijing starting ``start_hour`` local time (GMT+8 in October)."""
        arrival = datetime(2008, 10, day, start_hour, 0) - timedelta(hours=8)
        return {"lat": lat, "lon": lon, "arrival_time": arrival, "departure_time": arrival + timedelta(hours=hours)}

    def test_no_stay_in_any_window_is_unknown_without_evidence(self):
        result = HeuristicClassifier().predict([self._night(39.95, 116.35, 25, hours=3, start_hour=12)])  # Saturday noon
        for status in (result.home_status, result.office_status):
            assert (status.status, status.reason) == ("unknown", "no_candidate")
            assert status.window_minutes is None
            assert status.support is None

    def test_one_off_place_is_unknown_but_keeps_evidence(self):
        result = HeuristicClassifier().predict([self._night(39.98, 116.31, 22)])
        assert result.home is None
        assert result.home_status.status == "unknown"
        assert result.home_status.reason == "one_off_place"
        assert result.home_status.window_minutes == 600
        assert result.home_status.support == 1

    def test_few_window_minutes_is_unknown_even_when_repeated(self):
        # 22:00-01:00 on two nights at the same place: 180 min each, below the 240-minute minimum.
        stays = [self._night(39.98, 116.31, d, hours=3) for d in (22, 23)]
        result = HeuristicClassifier().predict(stays)
        assert result.home is None
        assert result.home_status.reason == "too_few_window_minutes"
        assert result.home_status.window_minutes == 180
        assert result.home_status.support == 2

    def test_support_counts_stays_within_200_m_without_changing_the_winner(self):
        near = self._night(39.9805, 116.3100, 23)      # about 60 m from the first one
        far = self._night(39.90, 116.40, 24, hours=12)
        first = self._night(39.9800, 116.3100, 22)
        result = HeuristicClassifier().predict([first, near, far])
        # ``far`` wins on minutes (the tie at 600 goes to the longer stay) but is a one-off.
        assert result.home is None
        assert result.home_status.reason == "one_off_place"
        assert result.home_status.support == 1
        result = HeuristicClassifier().predict([first, near])
        assert result.home_status.status == "found"
        assert result.home_status.support == 2
        assert result.home_status.reason is None

    def test_each_type_has_its_own_status(self):
        nights = [self._night(39.98, 116.31, d) for d in (22, 23)]
        office = [self._night(40.00, 116.33, 22, hours=9, start_hour=9)]          # a single work day
        result = HeuristicClassifier().predict(nights + office)
        assert result.home_status.status == "found"
        assert result.office_status.reason == "one_off_place"
        assert result.office is None


class TestWindowDays:
    """Days with window minutes, used by v2 to count how often a place is visited."""

    def test_night_belongs_to_the_day_it_opens(self):
        # Wednesday 23:00 -> Thursday 07:00 is the night of Wednesday only.
        home_days, office_days = HeuristicClassifier().window_days(datetime(2008, 10, 22, 23), datetime(2008, 10, 23, 7))
        assert home_days == {datetime(2008, 10, 22).date()}
        assert office_days == set()

    def test_early_morning_belongs_to_the_previous_night(self):
        home_days, _ = HeuristicClassifier().window_days(datetime(2008, 10, 23, 2), datetime(2008, 10, 23, 6))
        assert home_days == {datetime(2008, 10, 22).date()}
