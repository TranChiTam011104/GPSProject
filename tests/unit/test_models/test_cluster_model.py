"""Unit tests for the v2 classifier: DBSCAN places scored by v1's time windows (notebook 14)."""
from datetime import datetime, timedelta

import numpy as np

from gps.models.cluster import ClusterClassifier, place_labels
from gps.models.heuristic import HeuristicClassifier


def _stay(lat, lon, day, start_hour=22, hours=10, minute=0):
    """Stay in Beijing starting at local time (GMT+8 in October 2008)."""
    arrival = datetime(2008, 10, day, start_hour, minute) - timedelta(hours=8)
    return {"lat": lat, "lon": lon, "arrival_time": arrival, "departure_time": arrival + timedelta(hours=hours)}


class TestConfig:
    def test_defaults_come_from_notebook_14(self):
        classifier = ClusterClassifier()
        assert (classifier.eps_meters, classifier.min_samples, classifier.min_window_days) == (150.0, 2, 2)

    def test_config_overrides(self):
        classifier = ClusterClassifier({"eps_meters": 200.0, "min_samples": 5, "min_window_days": 3})
        assert (classifier.eps_meters, classifier.min_samples, classifier.min_window_days) == (200.0, 5, 3)

    def test_model_version(self):
        assert ClusterClassifier().get_model_version() == "v2-cluster-dbscan"


class TestPlaceLabels:
    def test_noise_stays_become_places_of_their_own(self):
        # Two stays ~60 m apart, one ~10 km away.
        labels = place_labels([39.9800, 39.9805, 39.90], [116.3100, 116.3100, 116.40], 150, 2)
        assert labels[0] == labels[1]
        assert labels[2] != labels[0]
        assert sorted(set(labels)) == [0, 1]

    def test_empty_input(self):
        assert len(place_labels([], [], 150, 2)) == 0

    def test_chain_of_neighbours_is_one_place(self):
        # 0.001 deg latitude ~ 111 m: each stay is within 150 m of the next, the ends ~333 m apart.
        lats = 39.98 + 0.001 * np.arange(4)
        assert len(set(place_labels(lats, [116.31] * 4, 150, 2))) == 1


class TestPlaces:
    def test_nights_at_nearby_spots_form_one_home(self):
        # Two nights ~60 m apart: v1 sees two one-off stays, v2 one place on two nights.
        nights = [_stay(39.9800, 116.3100, 22), _stay(39.9805, 116.3100, 23)]
        result = ClusterClassifier().predict(nights)
        assert result.home_status.status == "found"
        assert result.home_status.support == 2                # two nights
        assert result.home_status.window_minutes == 1200
        assert result.home.visit_count == 2
        assert result.home.confidence == 1.0
        assert abs(result.home.lat - 39.98025) < 1e-9          # duration-weighted centre

    def test_repeated_place_beats_a_longer_single_night(self):
        # v1 ties full nights and breaks the tie by the longer stay; v2 adds up the place's nights.
        repeated = [_stay(39.98, 116.31, d) for d in (22, 24)]           # 2 x 600 window minutes
        once = [_stay(39.90, 116.40, 23, start_hour=20, hours=14)]       # 600 window minutes, longer
        assert HeuristicClassifier().predict(repeated + once).home is None   # v1 picks the one-off
        result = ClusterClassifier().predict(repeated + once)
        assert result.home.lat == 39.98
        assert result.home.confidence == 1200 / 1800

    def test_two_stays_in_one_night_are_a_one_off(self):
        # Same place, same night, split in two stays: 570 window minutes but a single night.
        stays = [_stay(39.98, 116.31, 22, hours=4), _stay(39.98, 116.31, 23, start_hour=2, minute=30, hours=5.5)]
        result = ClusterClassifier().predict(stays)
        assert result.home is None
        assert result.home_status.reason == "one_off_place"
        assert result.home_status.support == 1
        assert result.home_status.window_minutes == 570

    def test_few_window_minutes_is_unknown_even_on_two_days(self):
        stays = [_stay(39.98, 116.31, d, hours=1.5) for d in (22, 23)]    # 90 min each
        result = ClusterClassifier().predict(stays)
        assert result.home_status.reason == "too_few_window_minutes"
        assert result.home_status.window_minutes == 180
        assert result.home_status.support == 2

    def test_no_candidate(self):
        result = ClusterClassifier().predict([_stay(39.95, 116.35, 25, start_hour=12, hours=3)])   # Saturday
        assert (result.home_status.reason, result.office_status.reason) == ("no_candidate", "no_candidate")

    def test_office_counts_work_days(self):
        days = [_stay(40.00, 116.33, d, start_hour=9, hours=9) for d in (22, 23)]   # Wed, Thu
        result = ClusterClassifier().predict(days)
        assert result.office_status.status == "found"
        assert result.office_status.support == 2
        assert result.home is None

    def test_pois_are_places_outside_both_windows(self):
        # Two Saturday afternoons at one mall and one Sunday at a park: two POI places.
        mall = [_stay(39.95, 116.35, d, start_hour=13, hours=3) for d in (25, 18)]
        park = [_stay(39.99, 116.29, 26, start_hour=10, hours=2)]
        result = ClusterClassifier().predict(mall + park)
        assert [p.visit_count for p in result.pois] == [2, 1]
        assert result.pois[0].confidence == 360 / 480
